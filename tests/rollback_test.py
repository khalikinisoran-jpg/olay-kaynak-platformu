import json

from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.controller.controller import Controller
from simulation.agent.controller.controller_decision import ControllerDecision
from simulation.agent.evidence.worker_evidence_recorder import (
    WorkerEvidenceRecorder
)
from simulation.agent.pipeline.apply_verify_pipeline import ApplyVerifyPipeline
from simulation.agent.pipeline.worker_action_pipeline import (
    FAILURE_ROLLBACK,
    WorkerActionPipeline,
)
from simulation.agent.recovery.bounded_recovery_engine import (
    BoundedRecoveryEngine
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


def make_verification_result(status=PASS, exit_code=0, reason=""):

    return VerificationResult(
        status=status,
        exit_code=exit_code,
        stdout="1 passed" if status == PASS else "1 failed",
        stderr="",
        command=("venv-python", "-m", "pytest", "-q"),
        failure_reason=reason,
    )


class FakeVerificationExecutor:

    def __init__(self, results):

        self.results = list(results)

        self.calls = []

    def verify(self, paths, test_targets=()):

        self.calls.append(tuple(paths))

        if not self.results:

            return make_verification_result()

        return self.results.pop(0)


class FreshMarkerWorker:

    def __init__(self, target):

        self.target = target

        self.allowed_paths = (str(target),)

        self.calls = 0

    def execute(self, agent, prompt, attempt=None, recovery_evidence=()):

        self.calls += 1

        content = self.target.read_text(encoding="utf-8")

        patch = PatchProposal(
            path=str(self.target),
            action="modify",
            reason="Rollback test.",
            old_content=content,
            new_content=content + f"\n# attempt {self.calls}\n",
            allowed_paths=self.allowed_paths,
        )

        return WorkerResult(
            task_id="rollback-task",
            success=True,
            summary="Rollback worker.",
            patches=(patch,),
        )


def approved_decision(patch):

    return Controller().approve(
        patch,
        ValidationResult(
            valid=True,
            message="Patch validation passed.",
        ),
    )


def build_kernel(tmp_path):

    store = EventStore(path=tmp_path / "events.jsonl")

    snapshot_manager = SnapshotManager(
        snapshot_store=SnapshotStore(
            path=tmp_path / "snapshot.json"
        )
    )

    return Kernel(store, snapshot_manager=snapshot_manager), store


def test_verification_failure_rolls_back_with_clean_verify(tmp_path):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    target.write_text(original, encoding="utf-8")

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Rollback test.",
        old_content=original,
        new_content="value = 2\n",
        allowed_paths=(str(target),),
    )

    pipeline = ApplyVerifyPipeline(
        verification_executor=FakeVerificationExecutor(
            [
                make_verification_result(
                    status=FAIL,
                    exit_code=2,
                    reason="tests failed",
                ),
            ]
        ),
    )

    result = pipeline.execute(
        patch,
        approved_decision(patch),
    )

    assert result.success is False

    assert result.rollback is not None

    assert result.rollback.success is True

    assert result.rollback.restore_verified is True

    assert (
        target.read_text(encoding="utf-8")
        == original
    )


def test_rollback_failure_is_terminal_not_retryable(tmp_path):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    target.write_text(original, encoding="utf-8")

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Rollback test.",
        old_content=original,
        new_content="value = 2\n",
        allowed_paths=(str(target),),
    )

    class FailingRollbackExecutor(ApplyExecutor):

        def rollback(self, patch):

            return (False, "restore target is gone")

    pipeline = WorkerActionPipeline(
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=FailingRollbackExecutor(),
            verification_executor=FakeVerificationExecutor(
                [
                    make_verification_result(
                        status=FAIL,
                        exit_code=2,
                        reason="tests failed",
                    ),
                ]
            ),
        ),
    )

    result = pipeline.execute(
        WorkerResult(
            task_id="rollback-task",
            success=True,
            summary="Rollback worker.",
            patches=(patch,),
        )
    )

    assert result.success is False

    assert result.failure_stage == FAILURE_ROLLBACK


def test_repeated_recovery_leaves_no_cumulative_modifications(tmp_path):

    target = tmp_path / "sample.txt"

    original = "value = 1\n"

    target.write_text(original, encoding="utf-8")

    worker = FreshMarkerWorker(target)

    pipeline = WorkerActionPipeline(
        apply_verify_pipeline=ApplyVerifyPipeline(
            verification_executor=FakeVerificationExecutor(
                [
                    make_verification_result(
                        status=FAIL,
                        exit_code=2,
                        reason="fails",
                    ),
                    make_verification_result(
                        status=FAIL,
                        exit_code=2,
                        reason="fails",
                    ),
                    make_verification_result(
                        status=FAIL,
                        exit_code=2,
                        reason="fails",
                    ),
                ]
            ),
        ),
    )

    engine = BoundedRecoveryEngine(
        worker=worker,
        worker_pipeline=pipeline,
        max_attempts=999,
    )

    result = engine.execute(
        agent=None,
        prompt="recover",
    )

    assert engine.max_attempts == 3

    assert result.terminal_failure is True

    assert result.attempts_used == 3

    assert worker.calls == 3

    assert (
        target.read_text(encoding="utf-8")
        == original
    )


def test_recovery_success_after_rollback_retry(tmp_path):

    target = tmp_path / "sample.txt"

    original = "value = 1\n"

    target.write_text(original, encoding="utf-8")

    worker = FreshMarkerWorker(target)

    pipeline = WorkerActionPipeline(
        apply_verify_pipeline=ApplyVerifyPipeline(
            verification_executor=FakeVerificationExecutor(
                [
                    make_verification_result(
                        status=FAIL,
                        exit_code=2,
                        reason="first attempt fails",
                    ),
                    make_verification_result(),
                ]
            ),
        ),
    )

    engine = BoundedRecoveryEngine(
        worker=worker,
        worker_pipeline=pipeline,
    )

    result = engine.execute(
        agent=None,
        prompt="recover",
    )

    assert result.success is True

    assert result.attempts_used == 2

    content = target.read_text(encoding="utf-8")

    assert "# attempt 1" not in content

    assert "# attempt 2" in content


def test_rollback_evidence_events_recorded(tmp_path):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    target.write_text(original, encoding="utf-8")

    patch = PatchProposal(
        path=str(target),
        action="modify",
        reason="Rollback evidence.",
        old_content=original,
        new_content="value = 2\n",
        allowed_paths=(str(target),),
    )

    kernel, store = build_kernel(tmp_path)

    recorder = WorkerEvidenceRecorder(kernel=kernel)

    pipeline = WorkerActionPipeline(
        apply_verify_pipeline=ApplyVerifyPipeline(
            verification_executor=FakeVerificationExecutor(
                [
                    make_verification_result(
                        status=FAIL,
                        exit_code=2,
                        reason="tests failed",
                    ),
                ]
            ),
        ),
        evidence_recorder=recorder,
    )

    result = pipeline.execute(
        WorkerResult(
            task_id="rollback-task",
            success=True,
            summary="Rollback worker.",
            patches=(patch,),
        )
    )

    assert result.success is False

    records = [
        json.loads(line)
        for line in store.path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    event_types = {
        record["event_type"]
        for record in records
    }

    assert "WorkerPatchApplied" in event_types

    assert "WorkerVerificationFailed" in event_types

    assert "WorkerRollbackSucceeded" in event_types

    rollback_events = [
        record
        for record in records
        if record["event_type"] == "WorkerRollbackSucceeded"
    ]

    assert rollback_events

    assert rollback_events[0]["payload"]["success"] is True

    assert rollback_events[0]["payload"]["restore_verified"] is True

    assert (
        target.read_text(encoding="utf-8")
        == original
    )
