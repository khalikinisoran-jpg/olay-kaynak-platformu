import json

import pytest

from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.controller.controller import Controller
from simulation.agent.controller.controller_decision import (
    ControllerDecision,
)
from simulation.agent.evidence.worker_events import (
    WorkerEventType,
)
from simulation.agent.evidence.worker_evidence_recorder import (
    WorkerEvidenceRecorder,
)
from simulation.agent.pipeline.apply_verify_pipeline import (
    ApplyVerifyPipeline,
)
from simulation.agent.pipeline.worker_action_pipeline import (
    WorkerActionPipeline,
)
from simulation.agent.recovery.bounded_recovery_engine import (
    BoundedRecoveryEngine,
)
from simulation.agent.verify.verification_result import (
    FAIL,
    PASS,
    VerificationResult,
)
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.agent.worker.patch_validator import PatchValidator
from simulation.agent.worker.validation_result import ValidationResult
from simulation.agent.worker.worker_result import WorkerResult
from simulation.core.kernel import Kernel
from simulation.persistence.event_store import EventStore
from simulation.persistence.snapshot import SnapshotStore
from simulation.persistence.snapshot_manager import SnapshotManager
from simulation.security.governance_evaluator import (
    GovernanceDecision,
)
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_level import RiskLevel
from simulation.security.risk_policy import RiskPolicy


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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


class FakeVerificationExecutor:

    def __init__(self, results=None):

        self.results = (
            list(results)
            if results is not None
            else [make_verification_result()]
        )

        self.calls = []

        self.compile_calls = []

    def verify(self, paths, test_targets=()):

        self.calls.append({
            "paths": tuple(paths),
            "test_targets": tuple(test_targets),
        })

        if not self.results:

            return make_verification_result()

        return self.results.pop(0)

    def verify_python_compile(self, paths):

        self.compile_calls.append({
            "paths": tuple(paths),
        })

        if not self.results:

            return make_verification_result()

        return self.results.pop(0)


def make_patch(
    target,
    original,
    updated,
    allowed_paths=None
):

    return PatchProposal(
        path=str(target),
        action="modify",
        reason="Mission H security test.",
        old_content=original,
        new_content=updated,
        allowed_paths=tuple(
            allowed_paths
            if allowed_paths is not None
            else (str(target),)
        ),
    )


def make_worker_result(
    *patches,
    success=True,
    task_id="mission-h"
):

    return WorkerResult(
        task_id=task_id,
        success=success,
        summary="Mission H worker proposal.",
        patches=tuple(patches),
    )


def make_controller_decision(patch, approval_id=""):

    return ControllerDecision(
        approved=True,
        reason="Mission H controller approval.",
        patch_fingerprint=patch.fingerprint(),
        approval_id=approval_id,
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


def build_governed_pipeline(
    recorder=None,
    store=None,
    scope=(),
    verification_executor=None,
    approval_store=None
):

    return WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=ApplyExecutor(
                approval_store=store
            ),
            verification_executor=(
                verification_executor
                if verification_executor is not None
                else FakeVerificationExecutor()
            ),
        ),
        evidence_recorder=recorder,
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
        approval_store=(
            store
            if approval_store is None
            else approval_store
        ),
        scope=scope,
    )


def build_governed_recovery(
    worker,
    verification_results,
    store,
    max_attempts=3,
    recorder=None,
    scope=(),
):

    pipeline = WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=ApplyExecutor(
                approval_store=store
            ),
            verification_executor=FakeVerificationExecutor(
                verification_results
            ),
        ),
        evidence_recorder=recorder,
        risk_engine=RiskEngine(),
        risk_policy=RiskPolicy(),
        approval_store=store,
        scope=scope,
    )

    return BoundedRecoveryEngine(
        worker=worker,
        worker_pipeline=pipeline,
        max_attempts=max_attempts,
        evidence_recorder=recorder,
    )


class MarkerWorker:

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

        patch = make_patch(
            self.target,
            content,
            content + f"\n# retry marker {self.calls}\n",
            self.allowed_paths,
        )

        return make_worker_result(patch)


class FixedWorker:

    """Returns the exact same patch on every attempt."""

    def __init__(self, patch):

        self.patch = patch

        self.calls = 0

    def execute(
        self,
        agent,
        prompt,
        attempt=None,
        recovery_evidence=()
    ):

        self.calls += 1

        return make_worker_result(self.patch)


def grant_approval(store, patch, attempt, risk_level):

    return store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level=risk_level,
        attempt=attempt,
        authorizer="mission-h-human",
        expires_at=3600,
    )


def make_low_patch(tmp_path):
    target = tmp_path / "notes.txt"
    target.write_text("value = 1\n", encoding="utf-8")
    return target, make_patch(target, "value = 1\n", "value = 2\n")


def make_medium_patch(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("value = 1\n", encoding="utf-8")
    return target, make_patch(target, "value = 1\n", "value = 2\n")


def make_high_patch(tmp_path):
    target = tmp_path / "settings.secret.txt"
    target.write_text("value = 1\n", encoding="utf-8")
    return target, make_patch(target, "value = 1\n", "value = 2\n")


def make_critical_patch(tmp_path):
    target = tmp_path / "secrets" / "app.pem"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("value = 1\n", encoding="utf-8")
    return target, make_patch(target, "value = 1\n", "value = 2\n")


def make_unknown_patch(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("value = 1\n", encoding="utf-8")
    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Mission H UNKNOWN probe.",
        old_content="value = 1\n",
        new_content="value = 1\x00value = 2\n",
        allowed_paths=(str(target),),
    )
    return target, patch


# ---------------------------------------------------------------------------
# H-001  Authoritative scope enforcement
# ---------------------------------------------------------------------------

def test_h001_malicious_proposal_cannot_expand_authoritative_scope(
    tmp_path
):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    victim = tmp_path / "victim.txt"

    victim.write_text("ORIGINAL\n", encoding="utf-8")

    patch = make_patch(
        victim,
        "ORIGINAL\n",
        "TAMPERED\n",
        allowed_paths=(str(victim),),
    )

    pipeline = WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=ApplyExecutor(),
            verification_executor=FakeVerificationExecutor(),
        ),
        scope=(str(scope_dir),),
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is False

    assert result.apply_success is False

    assert result.failure_stage == "validation"

    assert (
        victim.read_text(encoding="utf-8")
        == "ORIGINAL\n"
    )


def test_h001_authoritative_scope_enforced_at_write_boundary(
    tmp_path
):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    victim = tmp_path / "victim.txt"

    victim.write_text("ORIGINAL\n", encoding="utf-8")

    patch = make_patch(
        victim,
        "ORIGINAL\n",
        "TAMPERED\n",
        allowed_paths=(str(victim),),
    )

    executor = ApplyExecutor()

    decision = make_controller_decision(patch)

    result = executor.apply(
        patch,
        decision,
        scope=(str(scope_dir),),
    )

    assert result.success is False

    assert (
        victim.read_text(encoding="utf-8")
        == "ORIGINAL\n"
    )


def test_h001_proposal_cannot_smuggle_broader_declared_scope(
    tmp_path
):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    allowed = scope_dir / "allowed.txt"

    allowed.write_text("x\n", encoding="utf-8")

    outside = tmp_path / "outside.txt"

    outside.write_text("secret\n", encoding="utf-8")

    patch = make_patch(
        allowed,
        "x\n",
        "y\n",
        allowed_paths=(str(outside),),
    )

    validator = PatchValidator()

    ok, message = validator.validate(
        patch,
        scope=(str(scope_dir),),
    )

    assert ok is False

    assert "declared scope" in message

    assert allowed.read_text(encoding="utf-8") == "x\n"


def test_h001_in_scope_proposal_still_allowed_under_authority(
    tmp_path
):

    scope_dir = tmp_path / "scope"

    scope_dir.mkdir()

    allowed = scope_dir / "allowed.txt"

    allowed.write_text("x\n", encoding="utf-8")

    patch = make_patch(
        allowed,
        "x\n",
        "y\n",
        allowed_paths=(str(allowed),),
    )

    pipeline = WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=ApplyExecutor(),
            verification_executor=FakeVerificationExecutor(),
        ),
        scope=(str(scope_dir),),
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is True

    assert (
        allowed.read_text(encoding="utf-8")
        == "y\n"
    )


# ---------------------------------------------------------------------------
# H-002  Risk policy retry budget is enforced
# ---------------------------------------------------------------------------

def _always_fail_results(count):

    return [
        make_verification_result(
            status=FAIL,
            exit_code=2,
            failure_reason="always fails",
        )
        for _ in range(count)
    ]


def test_h002_low_verification_failure_cannot_exceed_three_attempts(
    tmp_path
):

    target, _ = make_low_patch(tmp_path)

    engine = build_governed_recovery(
        MarkerWorker(target),
        _always_fail_results(10),
        store=None,
        max_attempts=3,
        scope=(str(tmp_path),),
    )

    result = engine.execute(None, "probe")

    assert result.terminal_failure is True

    assert result.attempts_used == 3

    assert engine.worker.calls == 3

    assert result.max_attempts == 3


def test_h002_medium_verification_failure_cannot_exceed_two_attempts(
    tmp_path
):

    target, _ = make_medium_patch(tmp_path)

    engine = build_governed_recovery(
        MarkerWorker(target),
        _always_fail_results(10),
        store=None,
        max_attempts=3,
        scope=(str(tmp_path),),
    )

    result = engine.execute(None, "probe")

    assert result.terminal_failure is True

    assert result.attempts_used == 2

    assert engine.worker.calls == 2


def test_h002_high_cannot_enter_a_second_autonomous_retry(tmp_path):

    from simulation.agent.approval.approval_store import (
        ApprovalStore,
    )

    target, patch = make_high_patch(tmp_path)

    store = ApprovalStore()

    grant_approval(store, patch, attempt=1, risk_level="HIGH")

    engine = build_governed_recovery(
        FixedWorker(patch),
        _always_fail_results(2),
        store=store,
        max_attempts=3,
        scope=(str(tmp_path),),
    )

    result = engine.execute(None, "probe")

    assert result.terminal_failure is True

    assert result.attempts_used == 1

    assert engine.worker.calls == 1

    assert (
        target.read_text(encoding="utf-8")
        == "value = 1\n"
    )


def test_h002_critical_cannot_enter_a_second_autonomous_retry(
    tmp_path
):

    from simulation.agent.approval.approval_store import (
        ApprovalStore,
    )

    target, patch = make_critical_patch(tmp_path)

    store = ApprovalStore()

    grant_approval(store, patch, attempt=1, risk_level="CRITICAL")

    engine = build_governed_recovery(
        FixedWorker(patch),
        _always_fail_results(2),
        store=store,
        max_attempts=3,
        scope=(str(tmp_path),),
    )

    result = engine.execute(None, "probe")

    assert result.terminal_failure is True

    assert result.attempts_used == 1

    assert engine.worker.calls == 1

    assert (
        target.read_text(encoding="utf-8")
        == "value = 1\n"
    )


def test_h002_unknown_cannot_retry(tmp_path):

    from simulation.agent.approval.approval_store import (
        ApprovalStore,
    )

    target, patch = make_unknown_patch(tmp_path)

    store = ApprovalStore()

    engine = build_governed_recovery(
        FixedWorker(patch),
        _always_fail_results(1),
        store=store,
        max_attempts=3,
        scope=(str(tmp_path),),
    )

    result = engine.execute(None, "probe")

    assert result.terminal_failure is True

    assert result.attempts_used == 1

    assert result.failure_stage == "risk"

    assert engine.worker.calls == 1


def test_h002_global_hard_cap_remains_three(tmp_path):

    target, _ = make_low_patch(tmp_path)

    engine = build_governed_recovery(
        MarkerWorker(target),
        _always_fail_results(10),
        store=None,
        max_attempts=999,
        scope=(str(tmp_path),),
    )

    assert engine.max_attempts == 3

    result = engine.execute(None, "probe")

    assert result.terminal_failure is True

    assert result.attempts_used == 3

    assert engine.worker.calls == 3


def test_h002_caller_cannot_raise_policy_budget(tmp_path):

    target, _ = make_medium_patch(tmp_path)

    engine = build_governed_recovery(
        MarkerWorker(target),
        _always_fail_results(10),
        store=None,
        max_attempts=3,
        scope=(str(tmp_path),),
    )

    result = engine.execute(None, "probe")

    assert result.attempts_used == 2


def test_h002_caller_may_provide_a_smaller_limit(tmp_path):

    target, _ = make_low_patch(tmp_path)

    engine = build_governed_recovery(
        MarkerWorker(target),
        _always_fail_results(10),
        store=None,
        max_attempts=1,
        scope=(str(tmp_path),),
    )

    result = engine.execute(None, "probe")

    assert result.terminal_failure is True

    assert result.attempts_used == 1


def test_h002_duplicate_proposal_protection_still_works(tmp_path):

    from simulation.agent.approval.approval_store import (
        ApprovalStore,
    )

    target, patch = make_medium_patch(tmp_path)

    store = ApprovalStore()

    engine = build_governed_recovery(
        FixedWorker(patch),
        _always_fail_results(2),
        store=store,
        max_attempts=3,
        scope=(str(tmp_path),),
    )

    result = engine.execute(None, "probe")

    assert result.terminal_failure is True

    assert (
        "Duplicate proposal fingerprint"
        in result.failure_reason
    )

    assert (
        target.read_text(encoding="utf-8")
        == "value = 1\n"
    )


def test_h002_governance_decision_carries_policy_budget():

    for level, expected in (
        (RiskLevel.LOW, 3),
        (RiskLevel.MEDIUM, 2),
        (RiskLevel.HIGH, 1),
        (RiskLevel.CRITICAL, 1),
    ):

        decision = GovernanceDecision.from_assessment(
            RiskEngine().classify(
                None,
            ),
            RiskPolicy.from_level(level),
        )

        assert decision.max_attempts == expected

    denied = RiskPolicy.from_level(RiskLevel.UNKNOWN)

    assert denied.allowed is False

    assert denied.max_attempts == 0


# ---------------------------------------------------------------------------
# H-003  Governance decision evidence
# ---------------------------------------------------------------------------

def test_h003_risk_decision_recorded_as_worker_event(tmp_path):

    target, patch = make_low_patch(tmp_path)

    kernel, store = build_isolated_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    pipeline = build_governed_pipeline(
        recorder=recorder,
        store=None,
        scope=(str(target),),
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is True

    risk_events = [
        event
        for event in kernel.events
        if event.event_type
        == WorkerEventType.RISK_ASSESSED
    ]

    assert len(risk_events) == 1

    payload = risk_events[0].payload

    assert payload["risk_level"] == "LOW"

    assert payload["allowed"] is True

    assert payload["requires_human_approval"] is False

    assert payload["allow_auto_apply"] is True

    assert payload["max_attempts"] == 3

    assert payload["verification_depth"] == "compile+tests"

    assert payload["patch_fingerprint"] == patch.fingerprint()

    assert payload["reason"]

    assert payload["assessment_reason"]

    assert "old_content" not in payload

    assert "new_content" not in payload


def test_h003_high_decision_evidence_records_approval_requirements(
    tmp_path
):

    from simulation.agent.approval.approval_store import (
        ApprovalStore,
    )

    target, patch = make_high_patch(tmp_path)

    kernel, store = build_isolated_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    approval_store = ApprovalStore()

    grant_approval(
        approval_store,
        patch,
        attempt=1,
        risk_level="HIGH",
    )

    pipeline = build_governed_pipeline(
        recorder=recorder,
        store=approval_store,
        approval_store=approval_store,
        scope=(str(target),),
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is True

    risk_events = [
        event
        for event in kernel.events
        if event.event_type
        == WorkerEventType.RISK_ASSESSED
    ]

    assert len(risk_events) == 1

    payload = risk_events[0].payload

    assert payload["risk_level"] == "HIGH"

    assert payload["allowed"] is True

    assert payload["requires_human_approval"] is True

    assert payload["allow_auto_apply"] is False

    assert payload["max_attempts"] == 1


def test_h003_denied_proposal_still_records_decision_evidence(
    tmp_path
):

    target, patch = make_unknown_patch(tmp_path)

    kernel, store = build_isolated_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    pipeline = build_governed_pipeline(
        recorder=recorder,
        store=None,
        scope=(str(target),),
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is False

    risk_events = [
        event
        for event in kernel.events
        if event.event_type
        == WorkerEventType.RISK_ASSESSED
    ]

    assert len(risk_events) == 1

    assert risk_events[0].payload["risk_level"] == "UNKNOWN"

    assert risk_events[0].payload["allowed"] is False

    assert risk_events[0].payload["max_attempts"] == 0


def test_h003_evidence_payload_is_secret_safe(tmp_path):

    target = tmp_path / "settings.secret.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Mission H secret probe.",
        old_content="value = 1\n",
        new_content=(
            "password = 'TOPSECRETMARKER123'\nvalue = 2\n"
        ),
        allowed_paths=(str(target),),
    )

    kernel, store = build_isolated_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    pipeline = build_governed_pipeline(
        recorder=recorder,
        store=None,
        scope=(str(target),),
    )

    pipeline.execute(
        make_worker_result(patch)
    )

    risk_events = [
        event
        for event in kernel.events
        if event.event_type
        == WorkerEventType.RISK_ASSESSED
    ]

    assert len(risk_events) == 1

    serialized = json.dumps(
        risk_events[0].payload,
        sort_keys=True,
        ensure_ascii=False,
    )

    assert "TOPSECRETMARKER123" not in serialized

    assert "old_content" not in risk_events[0].payload

    assert "new_content" not in risk_events[0].payload

    assert "stdout" not in risk_events[0].payload

    assert "stderr" not in risk_events[0].payload


# ---------------------------------------------------------------------------
# Replay  (governance evidence survives replay from the event store)
# ---------------------------------------------------------------------------

def _recorded_risk_payloads(store, expected_event_type):

    payloads = []

    for line in store.path.read_text(
        encoding="utf-8"
    ).splitlines():

        if not line.strip():

            continue

        record = json.loads(line)

        if record["event_type"] == expected_event_type:

            payloads.append(record["payload"])

    return payloads


def test_replay_governance_evidence_survives_event_stream(tmp_path):

    from simulation.security.hash_verifier import HashVerifier

    target, patch = make_low_patch(tmp_path)

    kernel, store = build_isolated_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    pipeline = build_governed_pipeline(
        recorder=recorder,
        store=None,
        scope=(str(target),),
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is True

    records = [
        json.loads(line)
        for line in store.path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    assert HashVerifier().verify(records) is True

    original = _recorded_risk_payloads(
        store,
        WorkerEventType.RISK_ASSESSED,
    )

    assert len(original) == 1

    replayed_kernel, _ = build_isolated_kernel(tmp_path)

    trace = replayed_kernel.get_state().worker_trace

    risk_records = [
        record
        for record in trace
        if record["event_type"]
        == WorkerEventType.RISK_ASSESSED
    ]

    assert len(risk_records) == 1

    replayed = risk_records[0]["payload"]

    for key, value in original[0].items():

        assert replayed.get(key) == value, key

    assert replayed["risk_level"] == "LOW"

    assert replayed["max_attempts"] == 3

    assert replayed["allowed"] is True


def test_event_store_is_authoritative_not_decision_trace(tmp_path):

    target, patch = make_low_patch(tmp_path)

    kernel, store = build_isolated_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    pipeline = build_governed_pipeline(
        recorder=recorder,
        store=None,
        scope=(str(target),),
    )

    pipeline.execute(
        make_worker_result(patch)
    )

    persisted = _recorded_risk_payloads(
        store,
        WorkerEventType.RISK_ASSESSED,
    )

    assert len(persisted) == 1

    assert persisted[0]["max_attempts"] == 3

    assert persisted[0]["risk_level"] == "LOW"

    fresh = Kernel(
        EventStore(
            path=store.path
        ),
        snapshot_manager=SnapshotManager(
            snapshot_store=SnapshotStore(
                path=tmp_path / "snapshot.json"
            )
        ),
    )

    trace = fresh.get_state().worker_trace

    assert any(
        record["event_type"]
        == WorkerEventType.RISK_ASSESSED
        for record in trace
    )


def test_replay_produces_full_governed_event_sequence(tmp_path):

    target, patch = make_low_patch(tmp_path)

    kernel, store = build_isolated_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    pipeline = build_governed_pipeline(
        recorder=recorder,
        store=None,
        scope=(str(target),),
    )

    pipeline.execute(
        make_worker_result(patch)
    )

    original_types = [
        event.event_type
        for event in kernel.events
    ]

    assert WorkerEventType.RISK_ASSESSED in original_types

    replayed_kernel, _ = build_isolated_kernel(tmp_path)

    replayed_types = [
        record["event_type"]
        for record in replayed_kernel.get_state().worker_trace
    ]

    for event_type in original_types:

        if event_type.startswith("Worker"):

            assert event_type in replayed_types


def test_replay_recovery_run_reconstructs_governance_evidence(
    tmp_path
):

    from simulation.security.hash_verifier import HashVerifier

    target, _ = make_low_patch(tmp_path)

    kernel, store = build_isolated_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    engine = build_governed_recovery(
        MarkerWorker(target),
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                failure_reason="first attempt fails",
            ),
            make_verification_result(
                status=FAIL,
                exit_code=2,
                failure_reason="clean-state check",
            ),
            make_verification_result(),
        ],
        store=None,
        recorder=recorder,
        scope=(str(tmp_path),),
    )

    result = engine.execute(None, "probe")

    assert result.success is True

    assert result.attempts_used == 2

    records = [
        json.loads(line)
        for line in store.path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    assert HashVerifier().verify(records) is True

    replayed_kernel, _ = build_isolated_kernel(tmp_path)

    trace = replayed_kernel.get_state().worker_trace

    replayed_risk = [
        record
        for record in trace
        if record["event_type"]
        == WorkerEventType.RISK_ASSESSED
    ]

    assert len(replayed_risk) == 2

    assert all(
        record["payload"]["risk_level"] == "LOW"
        for record in replayed_risk
    )

    assert all(
        record["payload"]["max_attempts"] == 3
        for record in replayed_risk
    )

    replayed_attempts = [
        record
        for record in trace
        if record["event_type"]
        == WorkerEventType.RECOVERY_ATTEMPTED
    ]

    assert len(replayed_attempts) == 2


# ---------------------------------------------------------------------------
# Apply boundary  (new governance info cannot weaken it)
# ---------------------------------------------------------------------------

def test_apply_boundary_recomputes_risk_from_patch(tmp_path):

    from simulation.agent.approval.approval_store import (
        ApprovalStore,
    )

    target = tmp_path / "settings.secret.txt"

    target.write_text("value = 1\n", encoding="utf-8")

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Apply boundary recompute probe.",
        old_content="value = 1\n",
        new_content="password = 'hunter2'\n",
        allowed_paths=(str(target),),
    )

    decision = make_controller_decision(patch)

    executor = ApplyExecutor(
        approval_store=ApprovalStore()
    )

    result = executor.apply(patch, decision)

    assert result.success is False

    assert (
        target.read_text(encoding="utf-8")
        == "value = 1\n"
    )


def test_apply_boundary_rejects_forged_decision_metadata(tmp_path):

    from simulation.agent.approval.approval_store import (
        ApprovalStore,
    )

    target, patch = make_high_patch(tmp_path)

    forged = ControllerDecision(
        approved=True,
        reason="Forged claim.",
        patch_fingerprint=patch.fingerprint(),
    )

    executor = ApplyExecutor(
        approval_store=ApprovalStore()
    )

    result = executor.apply(patch, forged)

    assert result.success is False


# ---------------------------------------------------------------------------
# Verification boundary  (apply success is never verification success)
# ---------------------------------------------------------------------------

def test_verification_failure_rolls_back_and_clean_verifies(tmp_path):

    from simulation.agent.approval.approval_store import (
        ApprovalStore,
    )

    target, patch = make_low_patch(tmp_path)

    verify = FakeVerificationExecutor(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                failure_reason="tests fail",
            ),
        ]
    )

    pipeline = build_governed_pipeline(
        store=None,
        scope=(str(target),),
        verification_executor=verify,
        approval_store=ApprovalStore(),
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.apply_success is True

    assert result.verification_passed is False

    assert result.success is False

    assert len(verify.calls) == 1

    assert (
        target.read_text(encoding="utf-8")
        == "value = 1\n"
    )

    stage = result.patch_results[0]

    assert stage.pipeline_result.rollback is not None

    assert stage.pipeline_result.rollback.success is True

    assert stage.pipeline_result.rollback.clean_verified is True
