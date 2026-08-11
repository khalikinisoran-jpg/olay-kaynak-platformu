import json

import pytest

from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.controller.controller import Controller
from simulation.agent.evidence.worker_events import (
    WorkerEventType,
    build_worker_event,
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
from simulation.agent.recovery.recovery_assembly import (
    build_recovery_agent,
)
from simulation.agent.verify.verification_result import (
    FAIL,
    PASS,
    VerificationResult,
)
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.agent.worker.patch_validator import PatchValidator
from simulation.agent.worker.worker_agent import WorkerAgent
from simulation.agent.worker.worker_result import WorkerResult
from simulation.core.kernel import Kernel
from simulation.decision.decision_trace import DecisionTrace
from simulation.persistence.event_store import EventStore
from simulation.persistence.snapshot import SnapshotStore
from simulation.persistence.snapshot_manager import SnapshotManager
from simulation.security.hash_verifier import HashVerifier

from tests.fake_worker_analyzer import FakeWorkerAnalyzer


class RecordingKernel:

    def __init__(self):

        self.events = []

        self.decision_trace = DecisionTrace()

    def dispatch(self, event):

        self.events.append(event)

    def get_decision_trace(self):

        return self.decision_trace


class StubProvider:

    def chat(self, request):

        raise AssertionError(
            "No real LLM call expected in evidence test."
        )

    def get_model_name(self):

        return "stub"


class FakeVerificationExecutor:

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


def make_patch(target, original, updated, allowed_paths):

    return PatchProposal(
        path=str(target),
        action="modify",
        reason="Worker evidence test.",
        old_content=original,
        new_content=updated,
        allowed_paths=tuple(allowed_paths),
    )


def make_worker_result(patch, success=True):

    return WorkerResult(
        task_id="evidence-task",
        success=success,
        summary="Evidence worker proposal.",
        patches=(
            (patch,)
            if patch is not None
            else ()
        ),
    )


def build_traced_pipeline(
    recorder,
    verification_executor=None,
    apply_executor=None
):

    return WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=(
                apply_executor
                if apply_executor is not None
                else ApplyExecutor()
            ),
            verification_executor=(
                verification_executor
                if verification_executor is not None
                else FakeVerificationExecutor(
                    [make_verification_result()]
                )
            ),
        ),
        evidence_recorder=recorder,
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
    ), store


def test_recorder_records_lifecycle_events_in_order(tmp_path):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        updated,
        (str(target),)
    )

    kernel = RecordingKernel()

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    pipeline = build_traced_pipeline(recorder)

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is True

    event_types = [
        event.event_type
        for event in kernel.events
    ]

    assert event_types == [
        WorkerEventType.TASK_CREATED,
        WorkerEventType.INSPECTION_COMPLETED,
        WorkerEventType.PATCH_PROPOSED,
        WorkerEventType.PATCH_VALIDATED,
        WorkerEventType.PATCH_APPROVED,
        WorkerEventType.PATCH_APPLIED,
        WorkerEventType.VERIFICATION_COMPLETED,
    ]


def test_recorder_records_decision_trace_steps(tmp_path):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        "value = 2\n",
        (str(target),)
    )

    kernel = RecordingKernel()

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    pipeline = build_traced_pipeline(recorder)

    pipeline.execute(
        make_worker_result(patch)
    )

    stages = [
        step["stage"]
        for step in kernel.decision_trace.steps
    ]

    assert WorkerEventType.TASK_CREATED in stages

    assert WorkerEventType.PATCH_APPROVED in stages

    assert WorkerEventType.VERIFICATION_COMPLETED in stages


def test_validation_failure_records_no_apply_or_verification(tmp_path):

    target = tmp_path / "sample.py"

    target.write_text(
        "current content\n",
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        "stale old content\n",
        "new content\n",
        (str(target),)
    )

    kernel = RecordingKernel()

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    pipeline = build_traced_pipeline(recorder)

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is False

    event_types = [
        event.event_type
        for event in kernel.events
    ]

    assert WorkerEventType.PATCH_VALIDATED in event_types

    assert WorkerEventType.PATCH_APPROVED not in event_types

    assert WorkerEventType.PATCH_APPLIED not in event_types

    assert WorkerEventType.VERIFICATION_COMPLETED not in event_types


def test_controller_rejection_records_rejected_no_apply(tmp_path):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        "value = 2\n",
        (str(target),)
    )

    class RejectingController:

        def approve(self, patch, validation_message):

            from simulation.agent.controller.controller_decision import (
                ControllerDecision,
            )

            return ControllerDecision(
                approved=False,
                reason="Evidence test rejection.",
            )

    kernel = RecordingKernel()

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    pipeline = WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=RejectingController(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=ApplyExecutor(),
            verification_executor=FakeVerificationExecutor(
                [make_verification_result()]
            ),
        ),
        evidence_recorder=recorder,
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is False

    event_types = [
        event.event_type
        for event in kernel.events
    ]

    assert WorkerEventType.PATCH_REJECTED in event_types

    assert WorkerEventType.PATCH_APPLIED not in event_types

    assert WorkerEventType.VERIFICATION_COMPLETED not in event_types

    rejected = next(
        event
        for event in kernel.events
        if event.event_type == WorkerEventType.PATCH_REJECTED
    )

    assert rejected.payload["approved"] is False


def test_apply_failure_records_apply_failed_no_verification(tmp_path):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        "value = 2\n",
        (str(target),)
    )

    class FailingApplyExecutor:

        def apply(self, patch, decision):

            from simulation.agent.apply.apply_result import (
                ApplyResult,
            )

            return ApplyResult(
                success=False,
                path=patch.path,
                message="Evidence test apply failure.",
            )

    kernel = RecordingKernel()

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    pipeline = WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=FailingApplyExecutor(),
            verification_executor=FakeVerificationExecutor(
                [make_verification_result()]
            ),
        ),
        evidence_recorder=recorder,
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is False

    event_types = [
        event.event_type
        for event in kernel.events
    ]

    assert WorkerEventType.PATCH_APPLY_FAILED in event_types

    assert WorkerEventType.PATCH_APPLIED not in event_types

    assert WorkerEventType.VERIFICATION_COMPLETED not in event_types

    assert WorkerEventType.VERIFICATION_FAILED not in event_types


def test_verification_failure_records_verification_failed(tmp_path):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        updated,
        (str(target),)
    )

    kernel = RecordingKernel()

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    pipeline = build_traced_pipeline(
        recorder,
        verification_executor=FakeVerificationExecutor(
            [
                make_verification_result(
                    status=FAIL,
                    exit_code=2,
                    stdout="1 failed",
                    stderr="FAILED sample_test::test_x",
                    failure_reason=(
                        "Test execution verification returned "
                        "non-zero exit code 2."
                    ),
                ),
            ]
        ),
    )

    result = pipeline.execute(
        make_worker_result(patch)
    )

    assert result.success is False

    assert result.apply_success is True

    event_types = [
        event.event_type
        for event in kernel.events
    ]

    assert WorkerEventType.PATCH_APPLIED in event_types

    assert WorkerEventType.VERIFICATION_FAILED in event_types

    assert WorkerEventType.VERIFICATION_COMPLETED not in event_types

    failed = next(
        event
        for event in kernel.events
        if event.event_type == WorkerEventType.VERIFICATION_FAILED
    )

    assert failed.payload["status"] == FAIL

    assert failed.payload["exit_code"] == 2

    assert failed.payload["passed"] is False


def test_payloads_never_contain_patch_content_or_command_output(
    tmp_path
):

    target = tmp_path / "sample.py"

    original = "VALUE_A_SECRET_MARKER = 1\n"

    updated = "VALUE_B_SECRET_MARKER = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        updated,
        (str(target),)
    )

    kernel = RecordingKernel()

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    pipeline = build_traced_pipeline(
        recorder,
        verification_executor=FakeVerificationExecutor(
            [
                make_verification_result(
                    status=FAIL,
                    exit_code=2,
                    stdout="TOP_SECRET_OUTPUT_LEAK",
                    stderr="TOP_SECRET_ERROR_LEAK",
                    failure_reason=(
                        "Test execution verification returned "
                        "non-zero exit code 2."
                    ),
                ),
            ]
        ),
    )

    pipeline.execute(
        make_worker_result(patch)
    )

    for event in kernel.events:

        serialized = json.dumps(
            event.payload,
            sort_keys=True,
            ensure_ascii=False,
        )

        assert "VALUE_A_SECRET_MARKER" not in serialized

        assert "VALUE_B_SECRET_MARKER" not in serialized

        assert "TOP_SECRET_OUTPUT_LEAK" not in serialized

        assert "TOP_SECRET_ERROR_LEAK" not in serialized

        forbidden_keys = {
            "old_content",
            "new_content",
            "old_text",
            "new_text",
            "stdout",
            "stderr",
        }

        assert not forbidden_keys.intersection(
            event.payload.keys()
        )

    fingerprinted = [
        event
        for event in kernel.events
        if event.event_type in {
            WorkerEventType.PATCH_PROPOSED,
            WorkerEventType.PATCH_VALIDATED,
            WorkerEventType.PATCH_APPROVED,
            WorkerEventType.PATCH_APPLIED,
            WorkerEventType.VERIFICATION_FAILED,
        }
    ]

    assert fingerprinted

    for event in fingerprinted:

        digest = event.payload["patch_fingerprint"]

        assert len(digest) == 64

        int(digest, 16)


def test_default_pipeline_has_no_recorder():

    pipeline = WorkerActionPipeline()

    assert pipeline.evidence_recorder is None


def test_build_worker_event_rejects_unknown_type():

    with pytest.raises(ValueError):

        build_worker_event(
            "NotAWorkerEvent",
            {},
        )


def test_build_recovery_agent_wires_recorder(tmp_path):

    target = tmp_path / "sample.py"

    target.write_text(
        "value = 1\n",
        encoding="utf-8"
    )

    worker_executor = WorkerExecutorForTest(target)

    kernel = RecordingKernel()

    agent = build_recovery_agent(
        kernel,
        worker_executor=worker_executor,
        provider=StubProvider(),
    )

    assert agent.worker_pipeline is not None

    assert agent.recovery_engine is not None

    assert (
        agent.worker_pipeline.evidence_recorder is not None
    )

    assert (
        agent.recovery_engine.evidence_recorder is not None
    )


def test_hash_chain_integrity_after_pipeline_run(tmp_path):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    updated = "value = 2\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        updated,
        (str(target),)
    )

    kernel, store = build_isolated_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    pipeline = build_traced_pipeline(recorder)

    pipeline.execute(
        make_worker_result(patch)
    )

    records = []

    for line in store.path.read_text(
        encoding="utf-8"
    ).splitlines():

        records.append(
            json.loads(line)
        )

    assert records

    assert HashVerifier().verify(records) is True

    sequences = [
        record["sequence"]
        for record in records
    ]

    assert sequences == sorted(sequences)

    assert sequences == list(
        range(1, len(records) + 1)
    )

    assert all(
        record.get("current_hash")
        for record in records
    )


def test_replay_reconstructs_worker_trace(tmp_path):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    patch = make_patch(
        target,
        original,
        "value = 2\n",
        (str(target),)
    )

    kernel, store = build_isolated_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    pipeline = build_traced_pipeline(recorder)

    pipeline.execute(
        make_worker_result(patch)
    )

    expected_types = {
        WorkerEventType.TASK_CREATED,
        WorkerEventType.INSPECTION_COMPLETED,
        WorkerEventType.PATCH_PROPOSED,
        WorkerEventType.PATCH_VALIDATED,
        WorkerEventType.PATCH_APPROVED,
        WorkerEventType.PATCH_APPLIED,
        WorkerEventType.VERIFICATION_COMPLETED,
    }

    replayed_kernel, _ = build_isolated_kernel(tmp_path)

    trace = replayed_kernel.get_state().worker_trace

    assert trace

    traced_types = {
        record["event_type"]
        for record in trace
    }

    assert expected_types.issubset(traced_types)

    assert all(
        record["sequence"] > 0
        for record in trace
    )


class WorkerExecutorForTest:

    """Minimal worker executor used by assembly tests."""

    def __init__(self, target):

        self.target = target

        self.allowed_paths = (str(target),)

    def execute(
        self,
        agent,
        prompt,
        attempt=None,
        recovery_evidence=()
    ):

        content = self.target.read_text(
            encoding="utf-8"
        )

        patch = make_patch(
            self.target,
            content,
            content + "\n# evidence assembly marker\n",
            self.allowed_paths,
        )

        return make_worker_result(patch)


class FakeRecoveryWorker:

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
            content + f"\n# recovery marker {self.calls}\n",
            self.allowed_paths,
        )

        return make_worker_result(patch)


def test_recovery_records_attempts_and_final_outcome(tmp_path):

    target = tmp_path / "sample.py"

    target.write_text(
        "value = 1\n",
        encoding="utf-8"
    )

    fail_result = make_verification_result(
        status=FAIL,
        exit_code=2,
        failure_reason=(
            "Test execution verification returned "
            "non-zero exit code 2."
        ),
    )

    pass_result = make_verification_result()

    kernel, store = build_isolated_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    pipeline = build_traced_pipeline(
        recorder,
        verification_executor=FakeVerificationExecutor(
            [fail_result, pass_result]
        ),
    )

    engine = BoundedRecoveryEngine(
        worker=FakeRecoveryWorker(target),
        worker_pipeline=pipeline,
        evidence_recorder=recorder,
    )

    result = engine.execute(
        agent=None,
        prompt="worker: recover",
    )

    assert result.success is True

    assert result.attempts_used == 2

    assert result.retry_count == 1

    records = []

    for line in store.path.read_text(
        encoding="utf-8"
    ).splitlines():

        records.append(
            json.loads(line)
        )

    assert HashVerifier().verify(records) is True

    event_types = [
        record["event_type"]
        for record in records
    ]

    attempts = [
        record
        for record in records
        if record["event_type"]
        == WorkerEventType.RECOVERY_ATTEMPTED
    ]

    assert len(attempts) == 2

    assert attempts[0]["payload"]["attempt"] == 1

    assert attempts[0]["payload"]["status"] == "FAILED"

    assert attempts[1]["payload"]["attempt"] == 2

    assert attempts[1]["payload"]["status"] == "SUCCESS"

    succeeded = [
        record
        for record in records
        if record["event_type"]
        == WorkerEventType.RECOVERY_SUCCEEDED
    ]

    assert len(succeeded) == 1

    assert succeeded[0]["payload"]["success"] is True

    assert succeeded[0]["payload"]["attempts_used"] == 2

    content = target.read_text(
        encoding="utf-8"
    )

    assert "# recovery marker 1" in content

    assert "# recovery marker 2" in content
