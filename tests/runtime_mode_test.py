"""Deterministic runtime-mode lock test (MISSION-017 Phase 4).

The runtime exposes three distinct modes through the existing assembly
(no new abstraction is invented):

- PROPOSAL_ONLY: plain ``Agent(kernel)`` — no pipeline, no apply, no
  recovery. This is the DEFAULT and the safe fallback.
- RECOVERY: ``build_recovery_agent(...)`` without risk args — apply +
  verify + bounded recovery active, risk gate OFF.
- GOVERNED: ``build_recovery_agent(...)`` with risk_engine + risk_policy
  — risk gate ON, HIGH/CRITICAL require a valid human approval, apply is
  store-backed.

The tests lock the determinism of mode selection: identical assembly
inputs always yield the same mode, apply is never default-on, and the
gate never activates without BOTH risk components.
"""

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
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_policy import RiskPolicy

from tests.fake_worker_analyzer import FakeWorkerAnalyzer


class StubProvider:

    def chat(self, request):

        raise AssertionError(
            "No real LLM call expected in the runtime-mode test."
        )

    def get_model_name(self):

        return "stub"


class ScriptedVerification:

    def __init__(self, result=None):

        self.result = (
            result
            if result is not None
            else VerificationResult(
                status=PASS,
                exit_code=0,
                stdout="1 passed",
                stderr="",
                command=("venv-python", "-m", "pytest", "-q"),
            )
        )

    def verify(self, paths, test_targets=()):

        return self.result


class NoPatchWorker:

    def execute(
        self,
        agent,
        prompt,
        attempt=None,
        recovery_evidence=()
    ):

        return WorkerResult(
            task_id="mode-worker",
            success=True,
            summary="No mutation probe.",
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

    return Kernel(
        store,
        snapshot_manager=snapshot_manager,
    )


def build_proposal_only_agent(tmp_path):

    kernel = build_isolated_kernel(tmp_path)

    executor = WorkerExecutor(
        worker=WorkerAgent(
            analyzer=FakeWorkerAnalyzer()
        ),
        allowed_paths=(str(tmp_path / "sample.txt"),),
    )

    return Agent(
        kernel,
        dispatcher=StrategyDispatcher(
            worker_executor=executor
        ),
        provider=StubProvider(),
    )


def build_recovery_agent_plain(tmp_path):

    kernel = build_isolated_kernel(tmp_path)

    return build_recovery_agent(
        kernel,
        worker_executor=WorkerExecutor(
            worker=WorkerAgent(
                analyzer=FakeWorkerAnalyzer()
            ),
            allowed_paths=(str(tmp_path / "sample.txt"),),
        ),
        provider=StubProvider(),
    )


def build_governed_agent(tmp_path):

    kernel = build_isolated_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    return build_recovery_agent(
        kernel,
        worker_executor=WorkerExecutor(
            worker=WorkerAgent(
                analyzer=FakeWorkerAnalyzer()
            ),
            allowed_paths=(str(tmp_path / "sample.txt"),),
        ),
        provider=StubProvider(),
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
        evidence_recorder=recorder,
    )


# ---------------------------------------------------------------------------
# PROPOSAL_ONLY (default) is safe: no pipeline, no apply, no recovery
# ---------------------------------------------------------------------------

def test_proposal_only_mode_is_the_default(tmp_path):

    agent = build_proposal_only_agent(tmp_path)

    assert agent.worker_pipeline is None

    assert agent.recovery_engine is None

    assert not hasattr(agent, "risk_gate_enabled")


def test_proposal_only_never_mutates(tmp_path):

    target = tmp_path / "sample.txt"

    original = "value = 1\n"

    target.write_text(original, encoding="utf-8")

    agent = build_proposal_only_agent(tmp_path)

    result = agent.chat("worker: add a proposal marker")

    assert result.success is True

    assert result.patches

    assert target.read_text(encoding="utf-8") == original


def test_proposal_only_selection_is_deterministic(tmp_path):

    agents = [
        build_proposal_only_agent(tmp_path)
        for _ in range(2)
    ]

    for agent in agents:

        assert agent.worker_pipeline is None

        assert agent.recovery_engine is None


# ---------------------------------------------------------------------------
# RECOVERY: apply+verify+recovery active, risk gate OFF
# ---------------------------------------------------------------------------

def test_recovery_mode_activates_pipeline_gate_off(tmp_path):

    agent = build_recovery_agent_plain(tmp_path)

    assert agent.worker_pipeline is not None

    assert agent.recovery_engine is not None

    assert agent.worker_pipeline.risk_gate_enabled is False

    assert agent.worker_pipeline.approval_store is None


def test_recovery_mode_selection_is_deterministic(tmp_path):

    agents = [
        build_recovery_agent_plain(tmp_path)
        for _ in range(2)
    ]

    for agent in agents:

        assert agent.worker_pipeline.risk_gate_enabled is False


def test_recovery_mode_does_not_apply_without_patches(tmp_path):

    agent = build_recovery_agent_plain(tmp_path)

    agent.recovery_engine.worker = NoPatchWorker()

    result = agent.chat("worker: recovery no patch")

    assert result.success is False

    assert result.failure_stage == "worker"


# ---------------------------------------------------------------------------
# GOVERNED: risk gate ON, HIGH/CRITICAL require human approval
# ---------------------------------------------------------------------------

def test_governed_mode_activates_gate_and_store(tmp_path):

    agent = build_governed_agent(tmp_path)

    assert agent.worker_pipeline is not None

    assert agent.recovery_engine is not None

    assert agent.worker_pipeline.risk_gate_enabled is True

    assert isinstance(
        agent.worker_pipeline.approval_store,
        ApprovalStore,
    )


def test_governed_mode_high_without_approval_denies(tmp_path):

    target = tmp_path / "settings.secret.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Governed HIGH probe.",
        old_content="value = 1\n",
        new_content="value = 2\n",
        allowed_paths=(str(target),),
    )

    class FixedPatchWorker:

        allowed_paths = (str(target),)

        def execute(
            self,
            agent,
            prompt,
            attempt=None,
            recovery_evidence=()
        ):

            return WorkerResult(
                task_id="governed-probe",
                success=True,
                summary="Governed probe.",
                patches=(patch,),
            )

    kernel = build_isolated_kernel(tmp_path)

    agent = build_recovery_agent(
        kernel,
        worker_executor=FixedPatchWorker(),
        provider=StubProvider(),
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
        evidence_recorder=WorkerEvidenceRecorder(kernel=kernel),
    )

    result = agent.chat("worker: governed probe")

    assert result.success is False

    assert result.failure_stage == "approval"


def test_governed_mode_selection_is_deterministic(tmp_path):

    agents = [
        build_governed_agent(tmp_path)
        for _ in range(2)
    ]

    for agent in agents:

        assert agent.worker_pipeline.risk_gate_enabled is True


def test_gate_never_activates_with_only_risk_engine(tmp_path):

    kernel = build_isolated_kernel(tmp_path)

    agent = build_recovery_agent(
        kernel,
        worker_executor=WorkerExecutor(
            worker=WorkerAgent(
                analyzer=FakeWorkerAnalyzer()
            ),
            allowed_paths=(str(tmp_path / "sample.txt"),),
        ),
        provider=StubProvider(),
        risk_engine=RiskEngine(),
    )

    assert agent.worker_pipeline.risk_gate_enabled is False


def test_gate_never_activates_with_only_risk_policy(tmp_path):

    kernel = build_isolated_kernel(tmp_path)

    agent = build_recovery_agent(
        kernel,
        worker_executor=WorkerExecutor(
            worker=WorkerAgent(
                analyzer=FakeWorkerAnalyzer()
            ),
            allowed_paths=(str(tmp_path / "sample.txt"),),
        ),
        provider=StubProvider(),
        risk_policy=RiskPolicy(),
    )

    assert agent.worker_pipeline.risk_gate_enabled is False


# ---------------------------------------------------------------------------
# Ledger wiring: governed mode with an explicit ledger keeps durability
# ---------------------------------------------------------------------------

def test_governed_mode_with_ledger_is_durable(tmp_path):

    kernel = build_isolated_kernel(tmp_path)

    ledger_path = tmp_path / "ledger.jsonl"

    store = ApprovalStore(
        evidence_recorder=WorkerEvidenceRecorder(kernel=kernel),
        ledger=ApprovalLedger(path=ledger_path),
    )

    agent = build_recovery_agent(
        kernel,
        worker_executor=WorkerExecutor(
            worker=WorkerAgent(
                analyzer=FakeWorkerAnalyzer()
            ),
            allowed_paths=(str(tmp_path / "sample.txt"),),
        ),
        provider=StubProvider(),
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
        approval_store=store,
    )

    assert agent.worker_pipeline.risk_gate_enabled is True

    assert agent.worker_pipeline.approval_store is store

    assert ledger_path.exists() is True
