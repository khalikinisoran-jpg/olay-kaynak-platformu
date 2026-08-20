import json

from simulation.agent.agent import Agent
from simulation.agent.approval.approval_ledger import (
    ApprovalLedger
)
from simulation.agent.approval.approval_store import (
    ApprovalStore
)
from simulation.agent.evidence.worker_evidence_recorder import (
    WorkerEvidenceRecorder
)
from simulation.agent.executors.worker.worker_executor import (
    WorkerExecutor
)
from simulation.agent.recovery.recovery_assembly import (
    build_recovery_agent
)
from simulation.agent.strategy_dispatcher import StrategyDispatcher
from simulation.agent.verify.verification_result import (
    FAIL,
    PASS,
    VerificationResult,
)
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.agent.worker.worker_agent import WorkerAgent
from simulation.agent.worker.worker_result import WorkerResult
from simulation.core.kernel import Kernel
from simulation.persistence.event_store import EventStore
from simulation.persistence.snapshot import SnapshotStore
from simulation.persistence.snapshot_manager import SnapshotManager
from simulation.security.hash_verifier import HashVerifier
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_policy import RiskPolicy

from tests.fake_worker_analyzer import FakeWorkerAnalyzer


class StubProvider:

    def chat(self, request):

        raise AssertionError(
            "No real LLM call expected in "
            "the governed runtime test."
        )

    def get_model_name(self):

        return "stub"


class ScriptedVerification:

    def __init__(self, results):

        self.results = list(results)

        self.calls = []

    def verify(self, paths, test_targets=()):

        self.calls.append({
            "paths": tuple(paths),
            "test_targets": tuple(test_targets),
        })

        if not self.results:

            return make_verification_result()

        return self.results.pop(0)


class FixedPatchWorker:

    """Returns the exact same WorkerResult (same fingerprint)."""

    def __init__(self, patch):

        self.patch = patch

        self.calls = 0

        self.allowed_paths = tuple(
            patch.allowed_paths
        )

    def execute(
        self,
        agent,
        prompt,
        attempt=None,
        recovery_evidence=()
    ):

        self.calls += 1

        return WorkerResult(
            task_id="governed-fixed",
            success=True,
            summary="Governed fixed worker.",
            patches=(self.patch,),
        )


class FreshMarkerWorker:

    """Proposes a fresh patch per attempt (distinct fingerprint)."""

    def __init__(self, target):

        self.target = target

        self.allowed_paths = (str(target),)

        self.calls = 0

    def execute(
        self,
        agent,
        prompt,
        attempt=None,
        recovery_evidence=()
    ):

        self.calls += 1

        content = self.target.read_text(
            encoding="utf-8"
        )

        patch = PatchProposal(
            path=str(self.target),
            action="modify",
            reason="Governed fresh worker.",
            old_content=content,
            new_content=(
                content
                + f"\n# governed marker {self.calls}\n"
            ),
            allowed_paths=self.allowed_paths,
        )

        return WorkerResult(
            task_id="governed-fresh",
            success=True,
            summary="Governed fresh worker.",
            patches=(patch,),
        )


def make_verification_result(
    status=PASS,
    exit_code=0,
    failure_reason=""
):

    return VerificationResult(
        status=status,
        exit_code=exit_code,
        stdout="1 passed" if status == PASS else "1 failed",
        stderr="",
        command=("venv-python", "-m", "pytest", "-q"),
        failure_reason=failure_reason,
    )


def build_isolated_kernel(tmp_path):

    store = EventStore(
        path=tmp_path / "events.jsonl"
    )

    snapshot_manager = SnapshotManager(
        snapshot_store=SnapshotStore(
            path=tmp_path / "snapshot.json"
        )
    )

    return (
        Kernel(
            store,
            snapshot_manager=snapshot_manager,
        ),
        store,
    )


def build_governed_agent(
    tmp_path,
    worker_executor,
    verification_executor,
    store=None,
    ledger_path=None,
):

    kernel, store_out = build_isolated_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    approval_store = store

    if approval_store is None and ledger_path is not None:

        approval_store = ApprovalStore(
            evidence_recorder=recorder,
            ledger=ApprovalLedger(path=ledger_path),
        )

    agent = build_recovery_agent(
        kernel,
        worker_executor=worker_executor,
        provider=StubProvider(),
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
        approval_store=approval_store,
        verification_executor=verification_executor,
    )

    assert agent.worker_pipeline.risk_gate_enabled is True

    return agent, kernel, store_out, approval_store


def make_high_patch(tmp_path):

    target = tmp_path / "settings.secret.txt"

    original = "value = 1\n"

    target.write_text(original, encoding="utf-8")

    return target, PatchProposal(
        path=str(target),
        action="modify",
        reason="Governed HIGH proposal.",
        old_content=original,
        new_content="value = 2\n",
        allowed_paths=(str(target),),
    )


def make_critical_patch(tmp_path):

    target = tmp_path / "secrets" / "app.pem"

    target.parent.mkdir(parents=True, exist_ok=True)

    original = "value = 1\n"

    target.write_text(original, encoding="utf-8")

    return target, PatchProposal(
        path=str(target),
        action="modify",
        reason="Governed CRITICAL proposal.",
        old_content=original,
        new_content="value = 2\n",
        allowed_paths=(str(target),),
    )


def grant_for(patch, store, risk_level="HIGH", authorizer="human-governed"):

    return store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level=risk_level,
        attempt=1,
        authorizer=authorizer,
        expires_at=3600,
    )


# ---------------------------------------------------------------------------
# 1. Default runtime stays proposal-only (no mutation)
# ---------------------------------------------------------------------------

def test_default_runtime_is_proposal_only_no_mutation(tmp_path):

    target, patch = make_high_patch(tmp_path)

    original = target.read_text(encoding="utf-8")

    kernel, _ = build_isolated_kernel(tmp_path)

    worker_executor = WorkerExecutor(
        worker=WorkerAgent(
            analyzer=FakeWorkerAnalyzer()
        ),
        allowed_paths=(str(target),),
    )

    agent = Agent(
        kernel,
        dispatcher=StrategyDispatcher(
            worker_executor=worker_executor
        ),
        provider=StubProvider(),
    )

    result = agent.chat("worker: governed default test")

    assert agent.worker_pipeline is None

    assert agent.recovery_engine is None

    assert (
        target.read_text(encoding="utf-8")
        == original
    )

    assert result.success is True


# ---------------------------------------------------------------------------
# 2. Governed apply without approval -> DENY (HIGH)
# ---------------------------------------------------------------------------

def test_governed_high_without_approval_denies(tmp_path):

    target, patch = make_high_patch(tmp_path)

    original = target.read_text(encoding="utf-8")

    agent, kernel, store, approval_store = build_governed_agent(
        tmp_path,
        worker_executor=FixedPatchWorker(patch),
        verification_executor=ScriptedVerification(
            [make_verification_result()]
        ),
        ledger_path=str(tmp_path / "ledger.jsonl"),
    )

    result = agent.chat("worker: governed no approval")

    assert result.success is False

    assert result.failure_stage == "approval"

    assert (
        target.read_text(encoding="utf-8")
        == original
    )


# ---------------------------------------------------------------------------
# 3. Valid HIGH approval -> ALLOW
# ---------------------------------------------------------------------------

def test_governed_high_with_valid_approval_allows(tmp_path):

    target, patch = make_high_patch(tmp_path)

    agent, kernel, store, approval_store = build_governed_agent(
        tmp_path,
        worker_executor=FixedPatchWorker(patch),
        verification_executor=ScriptedVerification(
            [make_verification_result()]
        ),
        store=ApprovalStore(),
    )

    grant_for(patch, approval_store, risk_level="HIGH")

    result = agent.chat("worker: governed approve high")

    assert result.success is True

    assert result.final_apply_success is True

    assert result.final_verification_passed is True

    assert (
        target.read_text(encoding="utf-8")
        == "value = 2\n"
    )


# ---------------------------------------------------------------------------
# 4. Valid CRITICAL approval -> ALLOW
# ---------------------------------------------------------------------------

def test_governed_critical_with_valid_approval_allows(tmp_path):

    target, patch = make_critical_patch(tmp_path)

    agent, kernel, store, approval_store = build_governed_agent(
        tmp_path,
        worker_executor=FixedPatchWorker(patch),
        verification_executor=ScriptedVerification(
            [make_verification_result()]
        ),
        store=ApprovalStore(),
    )

    grant_for(patch, approval_store, risk_level="CRITICAL")

    result = agent.chat("worker: governed approve critical")

    assert result.success is True

    assert result.final_apply_success is True

    assert (
        target.read_text(encoding="utf-8")
        == "value = 2\n"
    )


# ---------------------------------------------------------------------------
# 5. Approval granted for a different patch -> DENY
# ---------------------------------------------------------------------------

def test_governed_wrong_patch_approval_denies(tmp_path):

    target, patch = make_high_patch(tmp_path)

    other = PatchProposal(
        path=patch.path,
        action=patch.action,
        reason="Different patch.",
        old_content=patch.old_content,
        new_content="value = 9\n",
        allowed_paths=patch.allowed_paths,
    )

    original = target.read_text(encoding="utf-8")

    approval_store = ApprovalStore()

    grant_for(other, approval_store, risk_level="HIGH")

    agent, kernel, store, _ = build_governed_agent(
        tmp_path,
        worker_executor=FixedPatchWorker(patch),
        verification_executor=ScriptedVerification(
            [make_verification_result()]
        ),
        store=approval_store,
    )

    result = agent.chat("worker: governed wrong patch")

    assert result.success is False

    assert result.failure_stage == "approval"

    assert (
        target.read_text(encoding="utf-8")
        == original
    )


# ---------------------------------------------------------------------------
# 6. Approval granted for a different path -> DENY
# ---------------------------------------------------------------------------

def test_governed_wrong_path_approval_denies(tmp_path):

    target, patch = make_high_patch(tmp_path)

    other_path = tmp_path / "other.secret.txt"

    original = "other = 1\n"

    other_path.write_text(original, encoding="utf-8")

    approval_store = ApprovalStore()

    grant_for(
        PatchProposal(
            path=str(other_path),
            action="modify",
            reason="Approval for another path.",
            old_content=original,
            new_content="other = 2\n",
            allowed_paths=(str(other_path),),
        ),
        approval_store,
        risk_level="HIGH",
    )

    agent, kernel, store, _ = build_governed_agent(
        tmp_path,
        worker_executor=FixedPatchWorker(patch),
        verification_executor=ScriptedVerification(
            [make_verification_result()]
        ),
        store=approval_store,
    )

    result = agent.chat("worker: governed wrong path")

    assert result.success is False

    assert result.failure_stage == "approval"


# ---------------------------------------------------------------------------
# 7. Risk downgrade denied: HIGH approval cannot cover a CRITICAL patch
# ---------------------------------------------------------------------------

def test_governed_risk_downgrade_denied(tmp_path):

    target, patch = make_critical_patch(tmp_path)

    original = target.read_text(encoding="utf-8")

    approval_store = ApprovalStore()

    grant_for(patch, approval_store, risk_level="HIGH")

    agent, kernel, store, _ = build_governed_agent(
        tmp_path,
        worker_executor=FixedPatchWorker(patch),
        verification_executor=ScriptedVerification(
            [make_verification_result()]
        ),
        store=approval_store,
    )

    result = agent.chat("worker: governed risk downgrade")

    assert result.success is False

    assert result.failure_stage == "approval"

    assert (
        target.read_text(encoding="utf-8")
        == original
    )


# ---------------------------------------------------------------------------
# 8. Consumed approval cannot authorize a second run (single-use)
# ---------------------------------------------------------------------------

def test_governed_approval_is_single_use_across_runs(tmp_path):

    target, patch = make_high_patch(tmp_path)

    approval_store = ApprovalStore()

    approval = grant_for(
        patch,
        approval_store,
        risk_level="HIGH",
    )

    verify = ScriptedVerification(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                failure_reason="first run fails verification",
            ),
        ]
    )

    worker = FixedPatchWorker(patch)

    agent, kernel, store, _ = build_governed_agent(
        tmp_path,
        worker_executor=worker,
        verification_executor=verify,
        store=approval_store,
    )

    first = agent.chat("worker: governed run one")

    assert first.success is False

    assert approval_store.is_consumed(approval) is True

    second = agent.chat("worker: governed run two")

    assert second.success is False

    assert second.failure_stage == "approval"

    assert (
        target.read_text(encoding="utf-8")
        == "value = 1\n"
    )


# ---------------------------------------------------------------------------
# 9. Verification failure -> controlled failure + rollback (no mutation)
# ---------------------------------------------------------------------------

def test_governed_verification_failure_rolls_back(tmp_path):

    target = tmp_path / "notes.txt"

    original = "value = 1\n"

    target.write_text(original, encoding="utf-8")

    verify = ScriptedVerification(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                failure_reason="always fails",
            ),
            make_verification_result(
                status=FAIL,
                exit_code=2,
                failure_reason="always fails",
            ),
            make_verification_result(
                status=FAIL,
                exit_code=2,
                failure_reason="always fails",
            ),
        ]
    )

    agent, kernel, store, approval_store = build_governed_agent(
        tmp_path,
        worker_executor=FreshMarkerWorker(target),
        verification_executor=verify,
        ledger_path=str(tmp_path / "ledger.jsonl"),
    )

    result = agent.chat("worker: governed rollback")

    assert result.success is False

    assert result.terminal_failure is True

    assert result.attempts_used == 3

    assert (
        target.read_text(encoding="utf-8")
        == original
    )


# ---------------------------------------------------------------------------
# 10. Evidence emitted through the hash-chained event store
# ---------------------------------------------------------------------------

def test_governed_run_emits_hash_chained_evidence(tmp_path):

    target, patch = make_high_patch(tmp_path)

    agent, kernel, store, approval_store = build_governed_agent(
        tmp_path,
        worker_executor=FixedPatchWorker(patch),
        verification_executor=ScriptedVerification(
            [make_verification_result()]
        ),
        ledger_path=str(tmp_path / "ledger.jsonl"),
    )

    grant_for(patch, approval_store, risk_level="HIGH")

    result = agent.chat("worker: governed evidence")

    assert result.success is True

    records = [
        json.loads(line)
        for line in store.path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    assert HashVerifier().verify(records) is True

    event_types = {
        record["event_type"]
        for record in records
    }

    assert "WorkerTaskCreated" in event_types

    assert "WorkerPatchProposed" in event_types

    assert "WorkerPatchApplied" in event_types

    assert "WorkerVerificationCompleted" in event_types

    assert "WorkerHumanApprovalGranted" in event_types


# ---------------------------------------------------------------------------
# 11. Consumed approval stays consumed after restart (ledger durability)
# ---------------------------------------------------------------------------

def test_governed_consumed_approval_not_reusable_after_restart(
    tmp_path
):

    target, patch = make_high_patch(tmp_path)

    ledger_path = str(tmp_path / "ledger.jsonl")

    verify = ScriptedVerification(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                failure_reason="first run fails",
            ),
        ]
    )

    worker = FixedPatchWorker(patch)

    agent, kernel, store, approval_store = build_governed_agent(
        tmp_path,
        worker_executor=worker,
        verification_executor=verify,
        ledger_path=ledger_path,
    )

    grant_for(patch, approval_store, risk_level="HIGH")

    first = agent.chat("worker: governed restart run one")

    assert first.success is False

    restarted_store = ApprovalStore(
        ledger=ApprovalLedger(path=ledger_path)
    )

    released = restarted_store.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        patch=patch,
    )

    assert released is None
