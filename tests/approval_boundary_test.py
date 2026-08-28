import pytest

from types import SimpleNamespace

from simulation.agent.apply.apply_authorization import (
    ApplyAuthorization
)

from simulation.agent.apply.apply_executor import ApplyExecutor

from simulation.agent.apply.apply_result import ApplyResult

from simulation.agent.approval.approval import (
    Approval,
    iso_in_past,
)

from simulation.agent.approval.approval_store import (
    ApprovalStore
)

from simulation.agent.controller.controller import Controller

from simulation.agent.controller.controller_decision import (
    ControllerDecision
)

from simulation.agent.evidence.worker_events import (
    WorkerEventType,
)

from simulation.agent.evidence.worker_evidence_recorder import (
    WorkerEvidenceRecorder
)

from simulation.agent.pipeline.apply_verify_pipeline import (
    ApplyVerifyPipeline
)

from simulation.agent.pipeline.worker_action_pipeline import (
    WorkerActionPipeline
)

from simulation.agent.verify.verification_result import (
    PASS,
    VerificationResult,
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)

from simulation.agent.worker.patch_validator import (
    PatchValidator
)

from simulation.agent.worker.validation_result import (
    ValidationResult
)

from simulation.agent.worker.worker_result import (
    WorkerResult
)

from simulation.security.risk_engine import (
    RiskEngine
)

from simulation.security.risk_level import (
    RiskLevel
)

from simulation.security.risk_policy import (
    RiskPolicy
)


class FakeVerificationExecutor:

    def __init__(self, result=None):

        self.result = (
            result
            if result is not None
            else make_verification_result()
        )

        self.calls = []

    def verify(self, paths, test_targets=()):

        self.calls.append({
            "paths": tuple(paths),
            "test_targets": tuple(test_targets),
        })

        return self.result


class RecordingApplyExecutor:

    def __init__(self, success=True):

        self.success = success

        self.calls = []

    def apply(self, patch, decision, attempt=None, scope=None):

        self.calls.append({
            "patch": patch,
            "decision": decision,
            "attempt": attempt,
        })

        return ApplyResult(
            success=self.success,
            path=patch.path,
            message=(
                "File applied successfully."
                if self.success
                else "File apply failed."
            ),
        )


class RecordingKernel:

    def __init__(self):

        self.events = []

    def dispatch(self, event):

        self.events.append(event)


class StubApprovalStore:

    def __init__(self, approval):

        self.approval = approval

    def find_valid(
        self,
        fingerprint,
        path=None,
        action=None,
        risk_level=None,
        attempt=None,
        patch=None,
    ):

        return self.approval


class ForgingApprovalStore:

    """Simulates an agent-controlled store that fabricates
    approval metadata from the query it is asked about."""

    def find_valid(
        self,
        fingerprint,
        path=None,
        action=None,
        risk_level=None,
        attempt=None,
        patch=None,
    ):

        return {
            "approved": True,
            "fingerprint": fingerprint,
            "path": path,
            "action": action,
            "risk_level": risk_level,
            "attempt": attempt,
        }


def make_verification_result(
    status=PASS,
    exit_code=0,
    stdout="",
    stderr="",
    failure_reason=""
):

    return VerificationResult(
        status=status,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        command=(
            "venv-python",
            "-m",
            "pytest",
            "-q",
        ),
        evidence=(),
        failure_reason=failure_reason,
    )


def make_patch(
    target,
    original,
    updated,
):

    return PatchProposal(
        path=str(target),
        action="modify",
        reason="Approval boundary test.",
        old_content=original,
        new_content=updated,
        allowed_paths=(str(target),),
    )


def make_worker_result(*patches):

    return WorkerResult(
        task_id="worker-task",
        success=True,
        summary="Approval boundary test.",
        patches=tuple(patches),
    )


def approved_decision(patch):

    return Controller().approve(
        patch,
        ValidationResult(
            valid=True,
            message="Patch validation passed.",
        ),
    )


def make_approval(
    patch,
    risk_level="HIGH",
    attempt=1,
    expires_at=None,
    authorizer="human-test",
    **overrides
):

    fields = {
        "patch_fingerprint": patch.fingerprint(),
        "path": patch.path,
        "action": patch.action,
        "risk_level": risk_level,
        "attempt": attempt,
        "authorizer": authorizer,
        "expires_at": (
            expires_at
            if expires_at is not None
            else ""
        ),
    }

    fields.update(overrides)

    return Approval(
        approval_id="fixed-approval-id",
        created_at="2026-08-12T00:00:00Z",
        **fields
    )


def build_gated_pipeline(
    apply_executor=None,
    approval_store=None,
    verification_executor=None,
    scope=(),
):

    return WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=(
                apply_executor
                if apply_executor is not None
                else RecordingApplyExecutor()
            ),
            verification_executor=(
                verification_executor
                if verification_executor is not None
                else FakeVerificationExecutor()
            ),
        ),
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
        approval_store=approval_store,
        scope=scope,
    )


def high_target(tmp_path):

    target = tmp_path / "settings.secret.txt"

    target.parent.mkdir(parents=True, exist_ok=True)

    return target


def critical_target(tmp_path):

    target = tmp_path / "secrets" / "app.pem"

    target.parent.mkdir(parents=True, exist_ok=True)

    return target


def write_target(target, content="value = 1\n"):

    target.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Approval model: fail-closed construction
# ---------------------------------------------------------------------------

def test_approval_construction_fails_closed_on_malformed_fields():

    patch_fp = "a" * 64

    base = {
        "approval_id": "id-1",
        "patch_fingerprint": patch_fp,
        "path": "/repo/app.py",
        "action": "modify",
        "risk_level": "HIGH",
        "attempt": 1,
        "authorizer": "human-1",
        "created_at": "2026-08-12T00:00:00Z",
        "expires_at": "",
    }

    Approval(**base)

    bad_fingerprint = dict(base, patch_fingerprint="a" * 63)

    with pytest.raises(ValueError):

        Approval(**bad_fingerprint)

    with pytest.raises(ValueError):

        Approval(**dict(base, path=""))

    with pytest.raises(ValueError):

        Approval(**dict(base, action=None))

    with pytest.raises(ValueError):

        Approval(**dict(base, risk_level="LOW"))

    with pytest.raises(ValueError):

        Approval(**dict(base, risk_level="UNKNOWN"))

    with pytest.raises(ValueError):

        Approval(**dict(base, attempt=0))

    with pytest.raises(ValueError):

        Approval(**dict(base, attempt="1"))

    with pytest.raises(ValueError):

        Approval(**dict(base, authorizer=""))

    with pytest.raises(ValueError):

        Approval(**dict(base, created_at="yesterday"))

    with pytest.raises(ValueError):

        Approval(**dict(base, expires_at="never"))


def test_approval_expiry_is_fail_closed():

    patch_fp = "b" * 64

    expired = Approval(
        approval_id="id-expired",
        patch_fingerprint=patch_fp,
        path="/repo/app.py",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        created_at=iso_in_past(3600),
        expires_at=iso_in_past(60),
    )

    assert expired.is_expired() is True

    valid = Approval(
        approval_id="id-valid",
        patch_fingerprint=patch_fp,
        path="/repo/app.py",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        created_at=iso_in_past(3600),
        expires_at="",
    )

    assert valid.is_expired() is False


# ---------------------------------------------------------------------------
# ApprovalStore: valid / missing / expired / replay / substitution
# ---------------------------------------------------------------------------

def test_approval_store_returns_valid_approval_for_full_context():

    store = ApprovalStore()

    fp = "c" * 64

    approval = store.grant(
        patch_fingerprint=fp,
        path="/repo/app.py",
        action="modify",
        risk_level="HIGH",
        attempt=2,
        authorizer="human-1",
        expires_at=3600,
    )

    found = store.find_valid(
        fp,
        path="/repo/app.py",
        action="modify",
        risk_level="HIGH",
        attempt=2,
    )

    assert found is not None

    assert found.approval_id == approval.approval_id

    assert found.patch_fingerprint == fp

    assert found.is_expired() is False


def test_approval_store_missing_approval_returns_none():

    store = ApprovalStore()

    assert (
        store.find_valid(
            "d" * 64,
            path="/repo/app.py",
            action="modify",
            risk_level="HIGH",
            attempt=1,
        )
        is None
    )


def test_approval_store_expired_approval_returns_none():

    store = ApprovalStore()

    store.grant(
        patch_fingerprint="e" * 64,
        path="/repo/app.py",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=-60,
    )

    assert (
        store.find_valid(
            "e" * 64,
            path="/repo/app.py",
            action="modify",
            risk_level="HIGH",
            attempt=1,
        )
        is None
    )


def test_approval_store_replayed_approval_is_consumed():

    store = ApprovalStore()

    store.grant(
        patch_fingerprint="f" * 64,
        path="/repo/app.py",
        action="modify",
        risk_level="CRITICAL",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    first = store.find_valid(
        "f" * 64,
        path="/repo/app.py",
        action="modify",
        risk_level="CRITICAL",
        attempt=1,
    )

    second = store.find_valid(
        "f" * 64,
        path="/repo/app.py",
        action="modify",
        risk_level="CRITICAL",
        attempt=1,
    )

    assert first is not None

    assert store.is_consumed(first) is True

    assert second is None


def test_approval_store_wrong_fingerprint_returns_none():

    store = ApprovalStore()

    store.grant(
        patch_fingerprint="01" * 32,
        path="/repo/app.py",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    assert (
        store.find_valid(
            "02" * 32,
            path="/repo/app.py",
            action="modify",
            risk_level="HIGH",
            attempt=1,
        )
        is None
    )


def test_approval_store_wrong_path_returns_none():

    store = ApprovalStore()

    store.grant(
        patch_fingerprint="03" * 32,
        path="/repo/app.py",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    assert (
        store.find_valid(
            "03" * 32,
            path="/repo/other.py",
            action="modify",
            risk_level="HIGH",
            attempt=1,
        )
        is None
    )


def test_approval_store_wrong_action_returns_none():

    store = ApprovalStore()

    store.grant(
        patch_fingerprint="04" * 32,
        path="/repo/app.py",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    assert (
        store.find_valid(
            "04" * 32,
            path="/repo/app.py",
            action="delete",
            risk_level="HIGH",
            attempt=1,
        )
        is None
    )


def test_approval_store_wrong_risk_context_returns_none():

    store = ApprovalStore()

    store.grant(
        patch_fingerprint="05" * 32,
        path="/repo/app.py",
        action="modify",
        risk_level="CRITICAL",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    assert (
        store.find_valid(
            "05" * 32,
            path="/repo/app.py",
            action="modify",
            risk_level="HIGH",
            attempt=1,
        )
        is None
    )


def test_approval_store_wrong_attempt_returns_none():

    store = ApprovalStore()

    store.grant(
        patch_fingerprint="06" * 32,
        path="/repo/app.py",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    assert (
        store.find_valid(
            "06" * 32,
            path="/repo/app.py",
            action="modify",
            risk_level="HIGH",
            attempt=2,
        )
        is None
    )


def test_approval_store_incomplete_context_query_fails_closed():

    store = ApprovalStore()

    store.grant(
        patch_fingerprint="07" * 32,
        path="/repo/app.py",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    assert store.find_valid("07" * 32) is None

    assert (
        store.find_valid(
            "07" * 32,
            path="/repo/app.py",
        )
        is None
    )

    assert (
        store.find_valid(
            "07" * 32,
            path="/repo/app.py",
            action="modify",
        )
        is None
    )

    assert (
        store.find_valid(
            "07" * 32,
            path="/repo/app.py",
            action="modify",
            risk_level="HIGH",
        )
        is None
    )

    assert (
        store.find_valid(
            "07" * 32,
            path="/repo/app.py",
            action="modify",
            risk_level="HIGH",
            attempt=1,
        )
        is not None
    )


# ---------------------------------------------------------------------------
# ApprovalStore: evidence integration
# ---------------------------------------------------------------------------

def test_approval_grant_records_evidence_event():

    kernel = RecordingKernel()

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    store = ApprovalStore(evidence_recorder=recorder)

    fp = "0a" * 32

    store.grant(
        patch_fingerprint=fp,
        path="/repo/app.py",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    assert len(kernel.events) == 1

    event = kernel.events[0]

    assert event.event_type == WorkerEventType.APPROVAL_GRANTED

    payload = event.payload

    assert payload["patch_fingerprint"] == fp

    assert payload["path"] == "/repo/app.py"

    assert payload["action"] == "modify"

    assert payload["risk_level"] == "HIGH"

    assert payload["attempt"] == 1

    assert payload["authorizer"] == "human-1"

    assert "old_content" not in payload

    assert "new_content" not in payload

    assert "old_text" not in payload

    assert "new_text" not in payload


def test_approval_grant_flows_through_real_kernel_hash_chain(
    tmp_path
):

    import json

    from simulation.core.kernel import Kernel

    from simulation.persistence.event_store import EventStore

    from simulation.persistence.snapshot import SnapshotStore

    from simulation.persistence.snapshot_manager import (
        SnapshotManager
    )

    from simulation.security.hash_verifier import (
        HashVerifier
    )

    store = EventStore(
        path=tmp_path / "events.jsonl"
    )

    snapshot_manager = SnapshotManager(
        snapshot_store=SnapshotStore(
            path=tmp_path / "snapshot.json"
        )
    )

    kernel = Kernel(
        store,
        snapshot_manager=snapshot_manager,
    )

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    approval_store = ApprovalStore(
        evidence_recorder=recorder
    )

    approval_store.grant(
        patch_fingerprint="0b" * 32,
        path="/repo/app.py",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    records = [
        json.loads(line)
        for line in store.path.read_text(
            encoding="utf-8"
        ).splitlines()
    ]

    assert records

    assert HashVerifier().verify(records) is True

    assert (
        records[-1]["event_type"]
        == "WorkerHumanApprovalGranted"
    )


def test_assembly_wires_approval_store_when_gate_enabled():

    from simulation.agent.recovery.recovery_assembly import (
        build_recovery_agent
    )

    class StubProvider:

        def chat(self, request):

            raise AssertionError("No real LLM call expected.")

        def get_model_name(self):

            return "stub"

    class StubWorkerExecutor:

        allowed_paths = ("tests/approval_boundary_test.py",)

        def execute(self, *args, **kwargs):

            raise AssertionError(
                "Worker executor not expected to run "
                "in the assembly construction test."
            )

    agent = build_recovery_agent(
        RecordingKernel(),
        worker_executor=StubWorkerExecutor(),
        provider=StubProvider(),
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
    )

    assert agent.worker_pipeline.risk_gate_enabled is True

    assert agent.worker_pipeline.approval_store is not None

    assert isinstance(
        agent.worker_pipeline.approval_store,
        ApprovalStore,
    )

    agent = build_recovery_agent(
        RecordingKernel(),
        worker_executor=StubWorkerExecutor(),
        provider=StubProvider(),
    )

    assert agent.worker_pipeline.risk_gate_enabled is False

    assert agent.worker_pipeline.approval_store is None


# ---------------------------------------------------------------------------
# Pipeline boundary: HIGH / CRITICAL without approval
# ---------------------------------------------------------------------------

def test_high_without_approval_denies(tmp_path):

    target = high_target(tmp_path)

    original = "value = 1\n"

    updated = "value = 2\n"

    write_target(target, original)

    apply_executor = RecordingApplyExecutor()

    pipeline = build_gated_pipeline(
        apply_executor=apply_executor,
        approval_store=ApprovalStore(),
        scope=(str(tmp_path),),
    )

    result = pipeline.execute(
        make_worker_result(
            make_patch(target, original, updated)
        )
    )

    assert result.success is False

    assert result.apply_success is False

    assert result.verification_ran is False

    assert result.failure_stage == "approval"

    assert result.patch_results[0].stage == "approval"

    assert apply_executor.calls == []

    assert target.read_text(encoding="utf-8") == original


def test_critical_without_approval_denies(tmp_path):

    target = critical_target(tmp_path)

    original = "value = 1\n"

    updated = "value = 2\n"

    write_target(target, original)

    apply_executor = RecordingApplyExecutor()

    pipeline = build_gated_pipeline(
        apply_executor=apply_executor,
        approval_store=ApprovalStore(),
        scope=(str(tmp_path),),
    )

    result = pipeline.execute(
        make_worker_result(
            make_patch(target, original, updated)
        )
    )

    assert result.success is False

    assert result.failure_stage == "approval"

    assert result.patch_results[0].stage == "approval"

    assert apply_executor.calls == []

    assert target.read_text(encoding="utf-8") == original


def test_high_without_any_store_denies(tmp_path):

    target = high_target(tmp_path)

    original = "value = 1\n"

    updated = "value = 2\n"

    write_target(target, original)

    apply_executor = RecordingApplyExecutor()

    pipeline = build_gated_pipeline(
        apply_executor=apply_executor,
        approval_store=None,
        scope=(str(tmp_path),),
    )

    result = pipeline.execute(
        make_worker_result(
            make_patch(target, original, updated)
        )
    )

    assert result.success is False

    assert result.failure_stage == "approval"

    assert (
        result.failure_reason
        == "High-risk patch requires human approval."
    )

    assert apply_executor.calls == []


# ---------------------------------------------------------------------------
# Pipeline boundary: HIGH / CRITICAL with valid approval
# ---------------------------------------------------------------------------

def test_high_with_valid_approval_allows_apply(tmp_path):

    target = high_target(tmp_path)

    original = "value = 1\n"

    updated = "value = 2\n"

    write_target(target, original)

    patch = make_patch(target, original, updated)

    store = ApprovalStore()

    store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    pipeline = build_gated_pipeline(
        apply_executor=ApplyExecutor(),
        approval_store=store,
        scope=(str(tmp_path),),
    )

    result = pipeline.execute(make_worker_result(patch))

    assert result.success is True

    assert result.apply_success is True

    assert result.verification_passed is True

    assert result.failure_stage == ""

    assert target.read_text(encoding="utf-8") == updated


def test_critical_with_valid_approval_allows_apply(tmp_path):

    target = critical_target(tmp_path)

    original = "value = 1\n"

    updated = "value = 2\n"

    write_target(target, original)

    patch = make_patch(target, original, updated)

    store = ApprovalStore()

    store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="CRITICAL",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    pipeline = build_gated_pipeline(
        apply_executor=ApplyExecutor(),
        approval_store=store,
        scope=(str(tmp_path),),
    )

    result = pipeline.execute(make_worker_result(patch))

    assert result.success is True

    assert result.apply_success is True

    assert result.failure_stage == ""

    assert target.read_text(encoding="utf-8") == updated


def test_pipeline_replayed_approval_denies_second_run(tmp_path):

    target = high_target(tmp_path)

    original = "value = 1\n"

    updated = "value = 2\n"

    write_target(target, original)

    patch = make_patch(target, original, updated)

    store = ApprovalStore()

    store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    apply_executor = RecordingApplyExecutor()

    pipeline = build_gated_pipeline(
        apply_executor=apply_executor,
        approval_store=store,
        scope=(str(tmp_path),),
    )

    first = pipeline.execute(make_worker_result(patch))

    assert first.success is True

    assert len(apply_executor.calls) == 1

    second = pipeline.execute(make_worker_result(patch))

    assert second.success is False

    assert second.failure_stage == "approval"

    assert second.patch_results[0].stage == "approval"

    assert len(apply_executor.calls) == 1


def test_pipeline_expired_approval_denies(tmp_path):

    target = high_target(tmp_path)

    original = "value = 1\n"

    updated = "value = 2\n"

    write_target(target, original)

    patch = make_patch(target, original, updated)

    store = ApprovalStore()

    store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=-60,
    )

    apply_executor = RecordingApplyExecutor()

    pipeline = build_gated_pipeline(
        apply_executor=apply_executor,
        approval_store=store,
        scope=(str(tmp_path),),
    )

    result = pipeline.execute(make_worker_result(patch))

    assert result.success is False

    assert result.failure_stage == "approval"

    assert apply_executor.calls == []


def test_pipeline_wrong_fingerprint_approval_denies(tmp_path):

    target = high_target(tmp_path)

    original = "value = 1\n"

    updated = "value = 2\n"

    write_target(target, original)

    patch = make_patch(target, original, updated)

    other = make_patch(
        target,
        original,
        "value = 99\n",
    )

    store = ApprovalStore()

    store.grant(
        patch_fingerprint=other.fingerprint(),
        path=other.path,
        action=other.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    apply_executor = RecordingApplyExecutor()

    pipeline = build_gated_pipeline(
        apply_executor=apply_executor,
        approval_store=store,
        scope=(str(tmp_path),),
    )

    result = pipeline.execute(make_worker_result(patch))

    assert result.success is False

    assert result.failure_stage == "approval"

    assert apply_executor.calls == []


# ---------------------------------------------------------------------------
# Pipeline boundary: substituted / malformed / forged approval
# ---------------------------------------------------------------------------

def test_pipeline_wrong_path_approval_denies(tmp_path):

    target = high_target(tmp_path)

    original = "value = 1\n"

    updated = "value = 2\n"

    write_target(target, original)

    patch = make_patch(target, original, updated)

    forged = make_approval(
        patch,
        path=str(tmp_path / "other.txt"),
    )

    pipeline = build_gated_pipeline(
        approval_store=StubApprovalStore(forged),
        scope=(str(tmp_path),),
    )

    result = pipeline.execute(make_worker_result(patch))

    assert result.success is False

    assert result.failure_stage == "approval"

    assert "different path" in result.failure_reason


def test_pipeline_wrong_action_approval_denies(tmp_path):

    target = high_target(tmp_path)

    original = "value = 1\n"

    updated = "value = 2\n"

    write_target(target, original)

    patch = make_patch(target, original, updated)

    forged = make_approval(
        patch,
        action="delete",
    )

    pipeline = build_gated_pipeline(
        approval_store=StubApprovalStore(forged),
        scope=(str(tmp_path),),
    )

    result = pipeline.execute(make_worker_result(patch))

    assert result.success is False

    assert result.failure_stage == "approval"

    assert "different action" in result.failure_reason


def test_pipeline_wrong_risk_context_approval_denies(tmp_path):

    target = high_target(tmp_path)

    original = "value = 1\n"

    updated = "value = 2\n"

    write_target(target, original)

    patch = make_patch(target, original, updated)

    forged = make_approval(
        patch,
        risk_level="CRITICAL",
    )

    pipeline = build_gated_pipeline(
        approval_store=StubApprovalStore(forged),
        scope=(str(tmp_path),),
    )

    result = pipeline.execute(make_worker_result(patch))

    assert result.success is False

    assert result.failure_stage == "approval"

    assert "different risk context" in result.failure_reason


def test_pipeline_wrong_attempt_approval_denies(tmp_path):

    target = high_target(tmp_path)

    original = "value = 1\n"

    updated = "value = 2\n"

    write_target(target, original)

    patch = make_patch(target, original, updated)

    store = ApprovalStore()

    store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    apply_executor = RecordingApplyExecutor()

    pipeline = build_gated_pipeline(
        apply_executor=apply_executor,
        approval_store=store,
        scope=(str(tmp_path),),
    )

    result = pipeline.execute(
        make_worker_result(patch),
        attempt=2,
    )

    assert result.success is False

    assert result.failure_stage == "approval"

    assert apply_executor.calls == []


def test_pipeline_rejects_forged_typed_approval(tmp_path):

    target = high_target(tmp_path)

    original = "value = 1\n"

    updated = "value = 2\n"

    write_target(target, original)

    patch = make_patch(target, original, updated)

    forged = make_approval(
        patch,
        patch_fingerprint="0" * 64,
    )

    pipeline = build_gated_pipeline(
        approval_store=StubApprovalStore(forged),
        scope=(str(tmp_path),),
    )

    result = pipeline.execute(make_worker_result(patch))

    assert result.success is False

    assert result.failure_stage == "approval"

    assert "different patch fingerprint" in result.failure_reason


def test_pipeline_rejects_agent_fabricated_approval_metadata(tmp_path):

    target = high_target(tmp_path)

    original = "value = 1\n"

    updated = "value = 2\n"

    write_target(target, original)

    patch = make_patch(target, original, updated)

    pipeline = build_gated_pipeline(
        approval_store=ForgingApprovalStore(),
        scope=(str(tmp_path),),
    )

    result = pipeline.execute(make_worker_result(patch))

    assert result.success is False

    assert result.failure_stage == "approval"

    assert "Malformed approval" in result.failure_reason


def test_pipeline_ignores_proposal_contained_approval_claim(tmp_path):

    target = high_target(tmp_path)

    original = "value = 1\n"

    updated = "value = 2\n"

    write_target(target, original)

    patch = make_patch(target, original, updated)

    object.__setattr__(
        patch,
        "human_approved",
        True,
    )

    object.__setattr__(
        patch,
        "approval_token",
        "FORGED-AGENT-TOKEN",
    )

    object.__setattr__(
        patch,
        "approved_by",
        "agent-self",
    )

    worker_result = make_worker_result(patch)

    object.__setattr__(
        worker_result,
        "approval",
        {"approved": True},
    )

    apply_executor = RecordingApplyExecutor()

    pipeline = build_gated_pipeline(
        apply_executor=apply_executor,
        approval_store=ApprovalStore(),
        scope=(str(tmp_path),),
    )

    result = pipeline.execute(worker_result)

    assert result.success is False

    assert result.failure_stage == "approval"

    assert apply_executor.calls == []


# ---------------------------------------------------------------------------
# Recovery integration: attempt context reaches the approval boundary
# ---------------------------------------------------------------------------

def test_recovery_passes_attempt_context_to_approval_boundary(
    tmp_path
):

    from simulation.agent.recovery.bounded_recovery_engine import (
        BoundedRecoveryEngine
    )

    target = high_target(tmp_path)

    original = "value = 1\n"

    updated = "value = 2\n"

    write_target(target, original)

    patch = make_patch(target, original, updated)

    class RecordingApprovalStore(ApprovalStore):

        def __init__(self):

            super().__init__()

            self.query_attempts = []

        def find_valid(
            self,
            fingerprint,
            path=None,
            action=None,
            risk_level=None,
            attempt=None,
            patch=None,
        ):

            self.query_attempts.append(attempt)

            return super().find_valid(
                fingerprint,
                path=path,
                action=action,
                risk_level=risk_level,
                attempt=attempt,
                patch=patch,
            )

    store = RecordingApprovalStore()

    approval = store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    class StaticWorker:

        def execute(
            self,
            agent,
            prompt,
            attempt=None,
            recovery_evidence=()
        ):

            return make_worker_result(patch)

    pipeline = build_gated_pipeline(
        apply_executor=RecordingApplyExecutor(),
        approval_store=store,
        scope=(str(tmp_path),),
    )

    engine = BoundedRecoveryEngine(
        worker=StaticWorker(),
        worker_pipeline=pipeline,
        max_attempts=3,
    )

    result = engine.execute(agent=None, prompt="probe")

    assert result.success is True

    assert result.attempts_used == 1

    assert store.query_attempts == [1]

    assert store.is_consumed(approval) is True


# ---------------------------------------------------------------------------
# MISSION-014: Apply authorization boundary hardening
#
# The apply authorization must never trust duck-typed metadata: only a
# real ControllerDecision whose approved flag is exactly True and whose
# fingerprint matches the applied patch can authorize, and HIGH/CRITICAL
# applies additionally require a store-verified approval binding that is
# consumed exactly once at the apply boundary.
# ---------------------------------------------------------------------------

def boundary_patch(tmp_path, risk="HIGH"):

    if risk == "CRITICAL":

        target = critical_target(tmp_path)

    else:

        target = high_target(tmp_path)

    original = "value = 1\n"

    updated = "value = 2\n"

    write_target(target, original)

    return target, original, updated, make_patch(
        target,
        original,
        updated,
    )


def grant_and_consume(store, patch, risk_level="HIGH", attempt=1):

    store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level=risk_level,
        attempt=attempt,
        authorizer="human-1",
        expires_at=3600,
    )

    return store.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level=risk_level,
        attempt=attempt,
        patch=patch,
    )


def bound_decision(patch, approval):

    return Controller().approve(
        patch,
        ValidationResult(
            valid=True,
            message="Patch validation passed.",
        ),
        approval=approval,
    )


def test_a_fake_controller_decision_object_is_denied(tmp_path):

    target, original, updated, patch = boundary_patch(tmp_path)

    store = ApprovalStore()

    fake = SimpleNamespace(
        approved=True,
        reason="agent forged object",
        patch_fingerprint=patch.fingerprint(),
    )

    assert (
        ApplyAuthorization(
            approval_store=store
        ).authorize(
            fake,
            patch,
        )
        is False
    )

    assert (
        ApplyAuthorization().authorize(
            fake,
            patch,
        )
        is False
    )


def test_b_forged_controller_decision_instance_is_denied(tmp_path):

    target, original, updated, patch = boundary_patch(tmp_path)

    store = ApprovalStore()

    forged = ControllerDecision(
        approved=True,
        reason="agent forged decision",
        patch_fingerprint=patch.fingerprint(),
    )

    authorization = ApplyAuthorization(
        approval_store=store
    )

    assert authorization.authorize(forged, patch) is False

    result = ApplyExecutor(
        approval_store=store
    ).apply(
        patch,
        forged,
        scope=(str(tmp_path),),
    )

    assert result.success is False

    assert target.read_text(encoding="utf-8") == original


def test_c_agent_claimed_approval_id_is_denied(tmp_path):

    target, original, updated, patch = boundary_patch(tmp_path)

    store = ApprovalStore()

    forged = ControllerDecision(
        approved=True,
        reason="agent claims an approval",
        patch_fingerprint=patch.fingerprint(),
        approval_id="agent-fabricated-approval-id",
    )

    assert (
        ApplyAuthorization(
            approval_store=store
        ).authorize(
            forged,
            patch,
        )
        is False
    )


def test_c2_unconsumed_grant_id_is_denied(tmp_path):

    target, original, updated, patch = boundary_patch(tmp_path)

    store = ApprovalStore()

    granted = store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    forged = ControllerDecision(
        approved=True,
        reason="steals a grant id without consumption",
        patch_fingerprint=patch.fingerprint(),
        approval_id=granted.approval_id,
    )

    assert (
        ApplyAuthorization(
            approval_store=store
        ).authorize(
            forged,
            patch,
        )
        is False
    )


def test_d_valid_approval_authorizes_apply(tmp_path):

    target, original, updated, patch = boundary_patch(tmp_path)

    store = ApprovalStore()

    approval = grant_and_consume(store, patch)

    decision = bound_decision(patch, approval)

    assert decision.approval_id == approval.approval_id

    result = ApplyExecutor(
        approval_store=store
    ).apply(
        patch,
        decision,
        scope=(str(tmp_path),),
    )

    assert result.success is True

    assert target.read_text(encoding="utf-8") == updated

    assert store.is_applied(approval) is True


def test_d2_valid_critical_approval_authorizes_apply(tmp_path):

    target, original, updated, patch = boundary_patch(
        tmp_path,
        risk="CRITICAL",
    )

    store = ApprovalStore()

    approval = grant_and_consume(
        store,
        patch,
        risk_level="CRITICAL",
    )

    decision = bound_decision(patch, approval)

    result = ApplyExecutor(
        approval_store=store
    ).apply(
        patch,
        decision,
        scope=(str(tmp_path),),
    )

    assert result.success is True

    assert target.read_text(encoding="utf-8") == updated

    assert store.is_applied(approval) is True


def test_e_approval_for_different_patch_is_denied(tmp_path):

    target, original, updated, patch = boundary_patch(tmp_path)

    other = make_patch(
        target,
        original,
        "value = 99\n",
    )

    store = ApprovalStore()

    approval = grant_and_consume(store, patch)

    decision = bound_decision(patch, approval)

    result = ApplyExecutor(
        approval_store=store
    ).apply(
        other,
        decision,
        scope=(str(tmp_path),),
    )

    assert result.success is False

    assert store.is_applied(approval) is False


def test_f_approval_for_different_path_is_denied(tmp_path):

    target, original, updated, patch = boundary_patch(tmp_path)

    sibling = high_target(tmp_path)

    other = make_patch(
        sibling,
        original,
        updated,
    )

    store = ApprovalStore()

    approval = grant_and_consume(store, patch)

    decision = bound_decision(patch, approval)

    assert (
        ApplyAuthorization(
            approval_store=store
        ).authorize(
            decision,
            other,
        )
        is False
    )


def test_g_approval_for_different_action_is_denied(tmp_path):

    target, original, updated, patch = boundary_patch(tmp_path)

    other = PatchProposal(
        path=patch.path,
        action="delete",
        reason=patch.reason,
        old_content=patch.old_content,
        new_content=patch.new_content,
        allowed_paths=patch.allowed_paths,
    )

    store = ApprovalStore()

    approval = grant_and_consume(store, patch)

    decision = bound_decision(patch, approval)

    assert (
        ApplyAuthorization(
            approval_store=store
        ).authorize(
            decision,
            other,
        )
        is False
    )


def test_h_approval_for_different_risk_is_denied(tmp_path):

    target, original, updated, patch = boundary_patch(tmp_path)

    critical = critical_target(tmp_path)

    write_target(critical, original)

    other = make_patch(
        critical,
        original,
        updated,
    )

    store = ApprovalStore()

    approval = grant_and_consume(store, patch)

    decision = bound_decision(patch, approval)

    assert (
        ApplyAuthorization(
            approval_store=store
        ).authorize(
            decision,
            other,
        )
        is False
    )


def test_i_approval_for_different_attempt_is_denied(tmp_path):

    target, original, updated, patch = boundary_patch(tmp_path)

    store = ApprovalStore()

    store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    found = store.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=2,
        patch=patch,
    )

    assert found is None


def test_j_approval_replay_at_apply_boundary_is_denied(tmp_path):

    target, original, updated, patch = boundary_patch(tmp_path)

    store = ApprovalStore()

    approval = grant_and_consume(store, patch)

    decision = bound_decision(patch, approval)

    authorization = ApplyAuthorization(
        approval_store=store
    )

    assert authorization.authorize(decision, patch) is True

    assert authorization.authorize(decision, patch) is False

    assert store.is_applied(approval) is True


def test_k_expired_approval_is_denied(tmp_path):

    target, original, updated, patch = boundary_patch(tmp_path)

    store = ApprovalStore()

    store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=-60,
    )

    approval = store.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        patch=patch,
    )

    assert approval is None

    forged = ControllerDecision(
        approved=True,
        reason="expired approval claim",
        patch_fingerprint=patch.fingerprint(),
        approval_id="any-id",
    )

    assert (
        ApplyAuthorization(
            approval_store=store
        ).authorize(
            forged,
            patch,
        )
        is False
    )


def test_l_malformed_approval_metadata_is_denied(tmp_path):

    target, original, updated, patch = boundary_patch(tmp_path)

    store = ApprovalStore()

    assert store.authorize_apply(None, patch) is False

    assert store.authorize_apply("", patch) is False

    forged = ControllerDecision(
        approved=True,
        reason="malformed approval claim",
        patch_fingerprint=patch.fingerprint(),
        approval_id=12345,
    )

    assert (
        ApplyAuthorization(
            approval_store=store
        ).authorize(
            forged,
            patch,
        )
        is False
    )


def test_m_evidence_only_authorization_is_denied(tmp_path):

    target, original, updated, patch = boundary_patch(tmp_path)

    store = ApprovalStore()

    forged = ControllerDecision(
        approved=True,
        reason="evidence records authority but is not authority",
        patch_fingerprint=patch.fingerprint(),
        approval_id="evidence-event-approval-id",
    )

    assert (
        ApplyAuthorization(
            approval_store=store
        ).authorize(
            forged,
            patch,
        )
        is False
    )


def test_n_approval_binding_is_object_identity(tmp_path):

    target, original, updated, patch = boundary_patch(tmp_path)

    twin = PatchProposal(
        path=patch.path,
        action=patch.action,
        reason=patch.reason,
        old_content=patch.old_content,
        new_content=patch.new_content,
        allowed_paths=patch.allowed_paths,
    )

    assert twin.fingerprint() == patch.fingerprint()

    assert twin is not patch

    store = ApprovalStore()

    approval = grant_and_consume(store, patch)

    decision = bound_decision(patch, approval)

    assert (
        ApplyAuthorization(
            approval_store=store
        ).authorize(
            decision,
            twin,
        )
        is False
    )


def test_o_direct_apply_authorization_bypass_is_denied(tmp_path):

    target, original, updated, patch = boundary_patch(tmp_path)

    store = ApprovalStore()

    forged = ControllerDecision(
        approved=True,
        reason="direct bypass attempt",
        patch_fingerprint=patch.fingerprint(),
    )

    assert (
        ApplyAuthorization(
            approval_store=store
        ).authorize(
            forged,
            patch,
        )
        is False
    )

    result = ApplyExecutor(
        approval_store=store
    ).apply(
        patch,
        forged,
        scope=(str(tmp_path),),
    )

    assert result.success is False

    assert target.read_text(encoding="utf-8") == original
