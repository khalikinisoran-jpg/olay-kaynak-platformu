import pytest

from pathlib import Path

from simulation.agent.agent import Agent
from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.apply.apply_result import ApplyResult
from simulation.agent.controller.controller import Controller
from simulation.agent.controller.controller_decision import ControllerDecision
from simulation.agent.executors.worker.worker_executor import WorkerExecutor
from simulation.agent.pipeline.apply_verify_pipeline import ApplyVerifyPipeline
from simulation.agent.pipeline.worker_action_pipeline import (
    FAILURE_APPLY,
    FAILURE_CONTROLLER,
    FAILURE_UNEXPECTED,
    FAILURE_VALIDATION,
    FAILURE_VERIFICATION,
    WorkerActionPipeline,
)
from simulation.agent.recovery.bounded_recovery_engine import BoundedRecoveryEngine
from simulation.agent.recovery.recovery_attempt import AttemptStatus
from simulation.agent.recovery.recovery_assembly import build_recovery_agent
from simulation.agent.recovery.recovery_result import RecoveryResult
from simulation.agent.strategy_dispatcher import StrategyDispatcher
from simulation.agent.verify.verification_result import (
    FAIL,
    PASS,
    VerificationEvidence,
    VerificationResult,
)
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.agent.worker.patch_validator import PatchValidator
from simulation.agent.worker.worker_agent import WorkerAgent
from simulation.agent.worker.worker_result import WorkerResult

from tests.fake_worker_analyzer import FakeWorkerAnalyzer


def make_verification_result(
    status=PASS,
    exit_code=0,
    stdout="",
    stderr="",
    evidence=(),
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
        evidence=tuple(evidence),
        failure_reason=failure_reason,
    )


def make_evidence(stage="tests", exit_code=2, marker="FAILED sample_test::test_x"):

    return VerificationEvidence(
        stage=stage,
        command=(
            "venv-python",
            "-m",
            "pytest",
            "-q",
        ),
        exit_code=exit_code,
        stdout=f"{marker} 1 failed",
        stderr=marker,
    )


class FakeVerificationExecutor:

    def __init__(self, results):

        self.results = list(results)

        self.calls = []

    def verify(
        self,
        paths,
        test_targets=()
    ):

        self.calls.append({
            "paths": tuple(paths),
            "test_targets": tuple(test_targets),
        })

        if not self.results:

            return make_verification_result()

        item = self.results.pop(0)

        if isinstance(item, Exception):

            raise item

        return item


class RecordingApplyExecutor:

    def __init__(self, success=True, message="File applied successfully."):

        self.success = success

        self.message = message

        self.calls = []

    def apply(
        self,
        patch,
        decision,
        attempt=None
    ):

        self.calls.append({
            "patch": patch,
            "decision": decision,
            "attempt": attempt,
        })

        return ApplyResult(
            success=self.success,
            path=patch.path,
            message=self.message,
        )


class RecordingController:

    def __init__(self, decisions=None):

        self.decisions = (
            list(decisions)
            if decisions is not None
            else []
        )

        self.calls = []

    def approve(
        self,
        patch,
        validation_message
    ):

        self.calls.append({
            "patch": patch,
            "validation_message": validation_message,
        })

        if self.decisions:

            return self.decisions.pop(0)

        return Controller().approve(
            patch,
            validation_message
        )


def make_patch(
    path,
    old_content,
    new_content,
    allowed_paths
):

    return PatchProposal(
        path=str(path),
        action="modify",
        reason="Recovery engine test.",
        old_content=old_content,
        new_content=new_content,
        allowed_paths=tuple(allowed_paths),
    )


def make_worker_result(patch, success=True):

    return WorkerResult(
        task_id="recovery-task",
        success=success,
        summary="Recovery worker proposal.",
        patches=(
            (patch,)
            if patch is not None
            else ()
        ),
    )


class FakeRecoveryWorker:

    """Worker used by the recovery engine.

    Every producer entry is either:

    - None           -> build a fresh valid patch from current content
    - WorkerResult   -> return exactly this result
    - Exception      -> raise it
    - callable(content) -> call it and return its WorkerResult

    The worker records every invocation, the attempt number and the
    recovery evidence it received, so the evidence hand-off contract
    can be asserted directly.
    """

    def __init__(self, target, producers):

        self.target = target

        self.allowed_paths = (str(target),)

        self.producers = list(producers)

        self.calls = 0

        self.received_attempts = []

        self.received_evidence = []

    def execute(
        self,
        agent,
        prompt,
        attempt=None,
        recovery_evidence=()
    ):

        self.calls += 1

        self.received_attempts.append(attempt)

        self.received_evidence.append(tuple(recovery_evidence))

        if not self.producers:

            return make_worker_result(None, success=False)

        item = self.producers.pop(0)

        if isinstance(item, Exception):

            raise item

        if isinstance(item, WorkerResult):

            return item

        content = self.target.read_text(
            encoding="utf-8"
        )

        if item is None:

            return self._fresh_result(content)

        return item(content)

    def _fresh_result(self, content):

        patch = make_patch(
            self.target,
            content,
            (
                content
                + f"\n# recovery marker {self.calls}\n"
            ),
            self.allowed_paths,
        )

        return make_worker_result(patch)


def build_pipeline(
    apply_executor,
    verification_executor,
    controller=None
):

    return WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=(
            controller
            if controller is not None
            else Controller()
        ),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=apply_executor,
            verification_executor=verification_executor,
        ),
    )


def build_engine(
    worker,
    pipeline,
    max_attempts=BoundedRecoveryEngine.DEFAULT_MAX_ATTEMPTS
):

    return BoundedRecoveryEngine(
        worker=worker,
        worker_pipeline=pipeline,
        max_attempts=max_attempts,
    )


def make_target(tmp_path, content="value = 1\n"):

    target = tmp_path / "sample.py"

    target.write_text(
        content,
        encoding="utf-8"
    )

    return target


def build_full_pipeline(verification_executor):

    return build_pipeline(
        ApplyExecutor(),
        verification_executor,
    )


def test_t01_verification_fail_creates_attempt_two(tmp_path):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(target, [None, None])

    verify = FakeVerificationExecutor(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                stdout="1 failed",
                stderr="FAILED test_one",
                evidence=(make_evidence(marker="FAILED test_one"),),
                failure_reason="Test execution verification returned "
                "non-zero exit code 2.",
            ),
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_full_pipeline(verify),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.success is True

    assert result.attempts_used == 2

    assert worker.calls == 2

    assert result.retry_count == 1

    assert len(result.attempt_history) == 2

    assert result.attempt_history[0].status == AttemptStatus.FAILED

    assert result.attempt_history[1].status == AttemptStatus.SUCCESS


def test_t02_two_fails_creates_attempt_three(tmp_path):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(target, [None, None, None])

    verify = FakeVerificationExecutor(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                evidence=(make_evidence(marker="FAILED one"),),
            ),
            make_verification_result(
                status=FAIL,
                exit_code=3,
                evidence=(make_evidence(marker="FAILED two"),),
            ),
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_full_pipeline(verify),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.success is True

    assert result.attempts_used == 3

    assert worker.calls == 3

    assert [
        attempt.status
        for attempt in result.attempt_history
    ] == [
        AttemptStatus.FAILED,
        AttemptStatus.FAILED,
        AttemptStatus.SUCCESS,
    ]


@pytest.mark.parametrize(
    "max_attempts",
    [
        BoundedRecoveryEngine.DEFAULT_MAX_ATTEMPTS,
        4,
        5,
    ],
)
def test_t03_three_fails_never_calls_worker_fourth_time(
    tmp_path, max_attempts
):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(target, [None, None, None])

    verify = FakeVerificationExecutor(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                evidence=(make_evidence(marker="FAILED one"),),
            ),
            make_verification_result(
                status=FAIL,
                exit_code=3,
                evidence=(make_evidence(marker="FAILED two"),),
            ),
            make_verification_result(
                status=FAIL,
                exit_code=4,
                evidence=(make_evidence(marker="FAILED three"),),
            ),
        ]
    )

    engine = build_engine(
        worker,
        build_full_pipeline(verify),
        max_attempts=max_attempts,
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.terminal_failure is True

    assert result.success is False

    assert worker.calls == 3

    assert len(verify.calls) == 3

    assert result.attempts_used == 3

    assert result.max_attempts == 3

    assert len(result.attempt_history) == 3

    assert len(worker.received_attempts) == 3

    assert worker.received_attempts == [1, 2, 3]

    assert all(
        attempt.status == AttemptStatus.FAILED
        for attempt in result.attempt_history
    )


def test_t04_first_attempt_pass_no_retry(tmp_path):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(target, [None])

    verify = FakeVerificationExecutor(
        [
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_full_pipeline(verify),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.success is True

    assert worker.calls == 1

    assert len(verify.calls) == 1

    assert result.retry_count == 0

    assert result.attempts_used == 1

    assert result.attempt_history[0].status == AttemptStatus.SUCCESS


def test_t05_validator_rejection_stops_no_worker_reanalysis(tmp_path):

    target = make_target(tmp_path)

    stale = make_worker_result(
        make_patch(
            target,
            "stale old content\n",
            "new content\n",
            (str(target),),
        )
    )

    worker = FakeRecoveryWorker(target, [stale])

    apply_executor = RecordingApplyExecutor()

    verify = FakeVerificationExecutor(
        [
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_pipeline(apply_executor, verify),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.terminal_failure is True

    assert worker.calls == 1

    assert apply_executor.calls == []

    assert verify.calls == []

    assert result.attempt_history[0].status == AttemptStatus.BLOCKED


def test_t06_controller_rejection_stops_no_worker_reanalysis(tmp_path):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(target, [None])

    rejection = ControllerDecision(
        approved=False,
        reason="Controller rejected validated patch."
    )

    controller = RecordingController(
        decisions=[rejection]
    )

    apply_executor = RecordingApplyExecutor()

    verify = FakeVerificationExecutor(
        [
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_pipeline(
            apply_executor,
            verify,
            controller=controller,
        ),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.terminal_failure is True

    assert worker.calls == 1

    assert apply_executor.calls == []

    assert verify.calls == []

    assert result.attempt_history[0].status == AttemptStatus.BLOCKED


def test_t07_apply_failure_no_verification_no_retry(tmp_path):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(target, [None])

    apply_executor = RecordingApplyExecutor(
        success=False,
        message="File is already in the requested state.",
    )

    verify = FakeVerificationExecutor(
        [
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_pipeline(apply_executor, verify),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.terminal_failure is True

    assert worker.calls == 1

    assert len(apply_executor.calls) == 1

    assert verify.calls == []

    assert result.retry_count == 0

    assert result.attempt_history[0].status == AttemptStatus.BLOCKED


def test_t08_failure_evidence_reaches_worker_and_new_proposal(tmp_path):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(target, [None, None])

    first_evidence = (
        make_evidence(marker="FAILED test_x"),
    )

    verify = FakeVerificationExecutor(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                stdout="1 failed",
                stderr="FAILED test_x",
                evidence=first_evidence,
                failure_reason="Test execution verification returned "
                "non-zero exit code 2.",
            ),
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_full_pipeline(verify),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.success is True

    assert worker.received_attempts == [1, 2]

    assert worker.received_evidence[0] == ()

    assert worker.received_evidence[1] == first_evidence

    assert result.attempt_history[0].evidence == first_evidence

    assert (
        result.attempt_history[0].worker_result.patches[0]
        is not result.attempt_history[1].worker_result.patches[0]
    )


def test_t09_duplicate_patch_is_not_blindly_reapplied(tmp_path):

    target = make_target(tmp_path)

    content = target.read_text(
        encoding="utf-8"
    )

    same_patch = make_patch(
        target,
        content,
        content + "\n# duplicate patch\n",
        (str(target),),
    )

    same_result = make_worker_result(same_patch)

    worker = FakeRecoveryWorker(
        target,
        [same_result, same_result],
    )

    apply_executor = RecordingApplyExecutor()

    verify = FakeVerificationExecutor(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                evidence=(make_evidence(),),
            ),
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_pipeline(apply_executor, verify),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.terminal_failure is True

    assert worker.calls == 2

    assert len(apply_executor.calls) == 1

    assert "Duplicate proposal fingerprint" in result.failure_reason

    assert result.attempt_history[1].status == AttemptStatus.BLOCKED


def test_t10_attempt_history_is_append_only_and_evidence_accessible(
    tmp_path
):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(target, [None, None, None])

    evidence_one = (make_evidence(marker="FAILED one"),)

    evidence_two = (make_evidence(marker="FAILED two"),)

    verify = FakeVerificationExecutor(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                evidence=evidence_one,
            ),
            make_verification_result(
                status=FAIL,
                exit_code=3,
                evidence=evidence_two,
            ),
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_full_pipeline(verify),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert len(result.attempt_history) == 3

    history = result.attempt_history

    assert history[0].attempt == 1

    assert history[1].attempt == 2

    assert history[2].attempt == 3

    assert history[0].evidence == evidence_one

    assert history[1].evidence == evidence_two

    assert history[0].evidence != history[1].evidence

    assert history[0].patch_fingerprints != ()

    assert (
        history[0].patch_fingerprints
        != history[1].patch_fingerprints
    )

    assert result.verification_evidence == history[2].evidence


def test_t11_huge_max_attempts_is_capped(tmp_path):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(
        target,
        [None, None, None, None, None],
    )

    verify = FakeVerificationExecutor(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                evidence=(make_evidence(marker="FAILED one"),),
            ),
            make_verification_result(
                status=FAIL,
                exit_code=3,
                evidence=(make_evidence(marker="FAILED two"),),
            ),
            make_verification_result(
                status=FAIL,
                exit_code=4,
                evidence=(make_evidence(marker="FAILED three"),),
            ),
            make_verification_result(
                status=FAIL,
                exit_code=5,
                evidence=(make_evidence(marker="FAILED four"),),
            ),
            make_verification_result(
                status=FAIL,
                exit_code=6,
                evidence=(make_evidence(marker="FAILED five"),),
            ),
        ]
    )

    engine = build_engine(
        worker,
        build_full_pipeline(verify),
        max_attempts=1_000_000,
    )

    assert engine.max_attempts == BoundedRecoveryEngine.MAX_ATTEMPTS_CAP

    assert engine.max_attempts < 1_000_000

    result = engine.execute(
        None,
        "recover"
    )

    assert result.terminal_failure is True

    assert result.attempts_used == BoundedRecoveryEngine.MAX_ATTEMPTS_CAP

    assert worker.calls == BoundedRecoveryEngine.MAX_ATTEMPTS_CAP

    assert len(verify.calls) == BoundedRecoveryEngine.MAX_ATTEMPTS_CAP

    assert len(result.attempt_history) == BoundedRecoveryEngine.MAX_ATTEMPTS_CAP


def test_t12_negative_max_attempts_falls_back_to_default(tmp_path):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(target, [None, None, None])

    verify = FakeVerificationExecutor(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                evidence=(make_evidence(),),
            ),
            make_verification_result(
                status=FAIL,
                exit_code=3,
                evidence=(make_evidence(),),
            ),
            make_verification_result(
                status=FAIL,
                exit_code=4,
                evidence=(make_evidence(),),
            ),
        ]
    )

    engine = build_engine(
        worker,
        build_full_pipeline(verify),
        max_attempts=-1,
    )

    assert engine.max_attempts == BoundedRecoveryEngine.DEFAULT_MAX_ATTEMPTS

    result = engine.execute(
        None,
        "recover"
    )

    assert result.terminal_failure is True

    assert result.attempts_used == BoundedRecoveryEngine.DEFAULT_MAX_ATTEMPTS

    assert worker.calls == BoundedRecoveryEngine.DEFAULT_MAX_ATTEMPTS


def test_t13_none_max_attempts_is_not_unlimited(tmp_path):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(target, [None, None, None])

    verify = FakeVerificationExecutor(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                evidence=(make_evidence(),),
            ),
            make_verification_result(
                status=FAIL,
                exit_code=3,
                evidence=(make_evidence(),),
            ),
            make_verification_result(
                status=FAIL,
                exit_code=4,
                evidence=(make_evidence(),),
            ),
        ]
    )

    engine = build_engine(
        worker,
        build_full_pipeline(verify),
        max_attempts=None,
    )

    assert engine.max_attempts == BoundedRecoveryEngine.DEFAULT_MAX_ATTEMPTS

    result = engine.execute(
        None,
        "recover"
    )

    assert result.terminal_failure is True

    assert result.attempts_used == BoundedRecoveryEngine.DEFAULT_MAX_ATTEMPTS

    assert worker.calls == BoundedRecoveryEngine.DEFAULT_MAX_ATTEMPTS


@pytest.mark.parametrize(
    "max_attempts",
    [
        4,
        5,
        1_000_000,
    ],
)
def test_t21_explicit_max_attempts_is_capped_to_three(
    tmp_path, max_attempts
):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(target, [None, None, None])

    verify = FakeVerificationExecutor(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                evidence=(make_evidence(marker="FAILED one"),),
            ),
            make_verification_result(
                status=FAIL,
                exit_code=3,
                evidence=(make_evidence(marker="FAILED two"),),
            ),
            make_verification_result(
                status=FAIL,
                exit_code=4,
                evidence=(make_evidence(marker="FAILED three"),),
            ),
        ]
    )

    engine = build_engine(
        worker,
        build_full_pipeline(verify),
        max_attempts=max_attempts,
    )

    assert engine.max_attempts == 3

    result = engine.execute(
        None,
        "recover"
    )

    assert result.terminal_failure is True

    assert result.success is False

    assert result.max_attempts == 3

    assert result.attempts_used == 3

    assert worker.calls == 3

    assert len(verify.calls) == 3

    assert len(result.attempt_history) == 3

    assert worker.calls < max_attempts

    assert len(worker.received_attempts) == 3

    assert worker.received_attempts == [1, 2, 3]


def test_MAX_ATTEMPTS_ENFORCED():

    engine = BoundedRecoveryEngine(
        worker=None,
        worker_pipeline=None,
    )

    assert BoundedRecoveryEngine.MAX_ATTEMPTS_CAP == 3

    assert BoundedRecoveryEngine.DEFAULT_MAX_ATTEMPTS == 3

    caller_values = (
        None,
        -1,
        0,
        1,
        2,
        3,
        4,
        5,
        1_000_000,
    )

    for value in caller_values:

        bounded = engine._bounded_max_attempts(value)

        assert 1 <= bounded <= BoundedRecoveryEngine.MAX_ATTEMPTS_CAP

    assert engine._bounded_max_attempts(None) == 3

    assert engine._bounded_max_attempts(-1) == 3

    assert engine._bounded_max_attempts(0) == 3

    assert engine._bounded_max_attempts(3) == 3

    assert engine._bounded_max_attempts(4) == 3

    assert engine._bounded_max_attempts(5) == 3

    assert engine._bounded_max_attempts(1_000_000) == 3


def test_t14_verification_exception_is_terminal_no_unlimited_loop(
    tmp_path
):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(target, [None])

    verify = FakeVerificationExecutor(
        [
            RuntimeError("verification exploded"),
        ]
    )

    engine = build_engine(
        worker,
        build_full_pipeline(verify),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.terminal_failure is True

    assert result.success is False

    assert worker.calls == 1

    assert len(verify.calls) == 1

    assert result.attempts_used == 1

    assert result.attempt_history[0].status == AttemptStatus.ERROR

    assert "exception" in result.failure_reason.lower()


def test_t15_worker_exception_on_attempt_two_is_terminal(tmp_path):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(
        target,
        [None, RuntimeError("worker crashed")],
    )

    verify = FakeVerificationExecutor(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                evidence=(make_evidence(),),
            ),
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_full_pipeline(verify),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.terminal_failure is True

    assert worker.calls == 2

    assert result.attempts_used == 2

    assert result.attempt_history[1].status == AttemptStatus.ERROR

    assert "worker exception" in result.failure_reason.lower()


class RecordingKernel:

    def __init__(self):

        self.events = []

    def dispatch(self, event):

        self.events.append(event)


class StubProvider:

    def chat(self, request):

        raise AssertionError(
            "No real LLM call expected during recovery test."
        )

    def get_model_name(self):

        return "stub"


def test_t16_default_agent_never_applies_or_verifies(tmp_path):

    target = make_target(tmp_path)

    apply_executor = RecordingApplyExecutor()

    verify = FakeVerificationExecutor(
        [
            make_verification_result(),
        ]
    )

    pipeline = build_pipeline(
        apply_executor,
        verify,
    )

    worker_executor = WorkerExecutor(
        worker=WorkerAgent(
            analyzer=FakeWorkerAnalyzer()
        ),
        allowed_paths=(str(target),),
    )

    dispatcher = StrategyDispatcher(
        worker_executor=worker_executor
    )

    agent = Agent(
        RecordingKernel(),
        dispatcher=dispatcher,
        provider=StubProvider(),
    )

    assert agent.worker_pipeline is None

    assert agent.recovery_engine is None

    result = agent.chat(
        "worker: add worker proposal marker"
    )

    assert isinstance(result, WorkerResult)

    assert result.success is True

    assert apply_executor.calls == []

    assert verify.calls == []

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == "value = 1\n"
    )


def test_t17_explicit_pipeline_pass_path_works(tmp_path):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(target, [None])

    verify = FakeVerificationExecutor(
        [
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_full_pipeline(verify),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert isinstance(result, RecoveryResult)

    assert result.success is True

    assert result.final_apply_success is True

    assert result.final_verification_passed is True

    assert result.final_apply_result is not None

    assert result.final_verification_result is not None

    content = target.read_text(
        encoding="utf-8"
    )

    assert "recovery marker 1" in content


def test_t18_attempt_one_fingerprint_cannot_authorize_attempt_two(
    tmp_path
):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(target, [None, None])

    apply_executor = RecordingApplyExecutor()

    verify = FakeVerificationExecutor(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                evidence=(make_evidence(),),
            ),
            make_verification_result(),
        ]
    )

    controller = RecordingController()

    engine = build_engine(
        worker,
        build_pipeline(
            apply_executor,
            verify,
            controller=controller,
        ),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.success is True

    assert len(apply_executor.calls) == 2

    call_one = apply_executor.calls[0]

    call_two = apply_executor.calls[1]

    fingerprint_one = call_one["patch"].fingerprint()

    fingerprint_two = call_two["patch"].fingerprint()

    assert fingerprint_one != fingerprint_two

    assert call_one["decision"].patch_fingerprint == fingerprint_one

    assert call_two["decision"].patch_fingerprint == fingerprint_two

    assert call_two["decision"] is not call_one["decision"]


def test_t19_out_of_scope_attempt_two_is_rejected_no_apply(tmp_path):

    target = make_target(tmp_path)

    outside = tmp_path / "outside.py"

    outside.write_text(
        "outside = 1\n",
        encoding="utf-8"
    )

    def out_of_scope_producer(content):

        return make_worker_result(
            make_patch(
                outside,
                "outside = 1\n",
                "outside = 2\n",
                (str(target),),
            )
        )

    worker = FakeRecoveryWorker(
        target,
        [None, out_of_scope_producer],
    )

    apply_executor = RecordingApplyExecutor()

    verify = FakeVerificationExecutor(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                evidence=(make_evidence(),),
            ),
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_pipeline(apply_executor, verify),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.terminal_failure is True

    assert worker.calls == 2

    assert len(apply_executor.calls) == 1

    assert apply_executor.calls[0]["patch"].path == str(target)

    assert "outside the allowed scope" in result.failure_reason

    assert result.attempt_history[1].status == AttemptStatus.BLOCKED


def test_t20_third_attempt_pass_terminal_success(tmp_path):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(target, [None, None, None])

    verify = FakeVerificationExecutor(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                evidence=(make_evidence(marker="FAILED one"),),
            ),
            make_verification_result(
                status=FAIL,
                exit_code=3,
                evidence=(make_evidence(marker="FAILED two"),),
            ),
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_full_pipeline(verify),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.success is True

    assert result.terminal_status == BoundedRecoveryEngine.STATUS_SUCCESS

    assert result.attempts_used == 3

    assert worker.calls == 3

    assert [
        attempt.status
        for attempt in result.attempt_history
    ] == [
        AttemptStatus.FAILED,
        AttemptStatus.FAILED,
        AttemptStatus.SUCCESS,
    ]


class ScriptedApplyExecutor:

    """Returns a scripted ApplyResult per apply call."""

    def __init__(self, outcomes):

        self.outcomes = list(outcomes)

        self.calls = []

    def apply(
        self,
        patch,
        decision,
        attempt=None
    ):

        self.calls.append(patch)

        return self.outcomes.pop(0)


def make_named_target(
    tmp_path,
    name,
    content="value = 1\n"
):

    target = tmp_path / name

    target.write_text(
        content,
        encoding="utf-8"
    )

    return target


def make_multi_worker_result(patch_a, patch_b):

    return WorkerResult(
        task_id="recovery-task",
        success=True,
        summary="Recovery worker multi-patch proposal.",
        patches=(patch_a, patch_b),
    )


class ExplodingPatch(PatchProposal):

    def fingerprint(self):

        raise RuntimeError("fingerprint exploded")


def test_m1_multi_patch_b_validation_fail_is_terminal_no_retry(
    tmp_path
):

    target_a = make_target(tmp_path)

    outside = tmp_path / "outside.py"

    outside.write_text(
        "outside = 1\n",
        encoding="utf-8"
    )

    patch_a = make_patch(
        target_a,
        "value = 1\n",
        "value = 1\n# recovery marker 1\n",
        (str(target_a),),
    )

    patch_b = make_patch(
        outside,
        "outside = 1\n",
        "outside = 2\n",
        (str(target_a),),
    )

    worker = FakeRecoveryWorker(
        target_a,
        [
            lambda content: make_multi_worker_result(
                patch_a,
                patch_b,
            )
        ],
    )

    apply_executor = RecordingApplyExecutor()

    verify = FakeVerificationExecutor(
        [
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_pipeline(
            apply_executor,
            verify,
        ),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.terminal_failure is True

    assert result.success is False

    assert worker.calls == 1

    assert result.retry_count == 0

    assert result.attempts_used == 1

    assert result.failure_stage == FAILURE_VALIDATION

    assert result.attempt_history[0].status == AttemptStatus.BLOCKED

    assert (
        result.attempt_history[0].failure_stage
        == FAILURE_VALIDATION
    )

    assert len(apply_executor.calls) == 1

    assert len(verify.calls) == 1

    assert (
        "outside the allowed scope"
        in result.failure_reason
    )


def test_m2_multi_patch_b_controller_reject_is_terminal_no_retry(
    tmp_path
):

    target_a = make_named_target(
        tmp_path,
        "alpha.py",
        "alpha = 1\n",
    )

    target_b = make_named_target(
        tmp_path,
        "beta.py",
        "beta = 1\n",
    )

    patch_a = make_patch(
        target_a,
        "alpha = 1\n",
        "alpha = 1\n# recovery marker\n",
        (str(target_a),),
    )

    patch_b = make_patch(
        target_b,
        "beta = 1\n",
        "beta = 2\n",
        (str(target_b),),
    )

    decision_a = ControllerDecision(
        approved=True,
        reason="Controller approved validated patch.",
        patch_fingerprint=patch_a.fingerprint(),
    )

    decision_b = ControllerDecision(
        approved=False,
        reason="Controller rejected validated patch.",
    )

    worker = FakeRecoveryWorker(
        target_a,
        [
            lambda content: make_multi_worker_result(
                patch_a,
                patch_b,
            )
        ],
    )

    controller = RecordingController(
        decisions=[decision_a, decision_b]
    )

    apply_executor = RecordingApplyExecutor()

    verify = FakeVerificationExecutor(
        [
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_pipeline(
            apply_executor,
            verify,
            controller=controller,
        ),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.terminal_failure is True

    assert result.success is False

    assert worker.calls == 1

    assert result.retry_count == 0

    assert result.attempts_used == 1

    assert result.failure_stage == FAILURE_CONTROLLER

    assert result.attempt_history[0].status == AttemptStatus.BLOCKED

    assert (
        result.attempt_history[0].failure_stage
        == FAILURE_CONTROLLER
    )

    assert len(apply_executor.calls) == 1

    assert len(verify.calls) == 1

    assert (
        "Controller rejected validated patch."
        in result.failure_reason
    )


def test_m3_multi_patch_b_apply_fail_is_terminal_no_verification(
    tmp_path
):

    target_a = make_named_target(
        tmp_path,
        "alpha.py",
        "alpha = 1\n",
    )

    target_b = make_named_target(
        tmp_path,
        "beta.py",
        "beta = 1\n",
    )

    patch_a = make_patch(
        target_a,
        "alpha = 1\n",
        "alpha = 1\n# recovery marker\n",
        (str(target_a),),
    )

    patch_b = make_patch(
        target_b,
        "beta = 1\n",
        "beta = 2\n",
        (str(target_b),),
    )

    worker = FakeRecoveryWorker(
        target_a,
        [
            lambda content: make_multi_worker_result(
                patch_a,
                patch_b,
            )
        ],
    )

    apply_executor = ScriptedApplyExecutor(
        [
            ApplyResult(
                success=True,
                path=str(target_a),
                message="File applied successfully.",
            ),
            ApplyResult(
                success=False,
                path=str(target_b),
                message="File is already in the requested state.",
            ),
        ]
    )

    verify = FakeVerificationExecutor(
        [
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_pipeline(
            apply_executor,
            verify,
        ),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.terminal_failure is True

    assert result.success is False

    assert worker.calls == 1

    assert result.retry_count == 0

    assert result.attempts_used == 1

    assert result.failure_stage == FAILURE_APPLY

    assert result.attempt_history[0].status == AttemptStatus.BLOCKED

    assert (
        result.attempt_history[0].failure_stage
        == FAILURE_APPLY
    )

    assert len(apply_executor.calls) == 2

    assert len(verify.calls) == 1

    assert "already in the requested state" in result.failure_reason


def test_m4_multi_patch_b_verification_fail_retries_bounded(
    tmp_path
):

    target_a = make_named_target(
        tmp_path,
        "alpha.py",
        "alpha = 1\n",
    )

    target_b = make_named_target(
        tmp_path,
        "beta.py",
        "beta = 1\n",
    )

    def multi_fresh(content):

        calls[0] += 1

        marker = f"\n# recovery marker {calls[0]}\n"

        patches = []

        for path_value in (
            str(target_a),
            str(target_b),
        ):

            current = Path(
                path_value
            ).read_text(
                encoding="utf-8"
            )

            patches.append(
                make_patch(
                    path_value,
                    current,
                    current + marker,
                    (path_value,),
                )
            )

        return make_multi_worker_result(
            patches[0],
            patches[1],
        )

    calls = [0]

    worker = FakeRecoveryWorker(
        target_a,
        [multi_fresh, multi_fresh],
    )

    verify = FakeVerificationExecutor(
        [
            make_verification_result(),
            make_verification_result(
                status=FAIL,
                exit_code=2,
                evidence=(
                    make_evidence(marker="FAILED beta"),
                ),
                failure_reason="Verification failed for beta.",
            ),
            make_verification_result(),
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_full_pipeline(verify),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.success is True

    assert worker.calls == 2

    assert result.attempts_used == 2

    assert result.retry_count == 1

    assert (
        result.attempt_history[0].status
        == AttemptStatus.FAILED
    )

    assert (
        result.attempt_history[0].failure_stage
        == FAILURE_VERIFICATION
    )

    assert (
        result.attempt_history[1].status
        == AttemptStatus.SUCCESS
    )

    assert worker.received_attempts == [1, 2]


def test_t30_single_patch_verification_fail_terminal_stage(tmp_path):

    target = make_target(tmp_path)

    worker = FakeRecoveryWorker(
        target,
        [None, None, None],
    )

    verify = FakeVerificationExecutor(
        [
            make_verification_result(
                status=FAIL,
                exit_code=2,
                evidence=(make_evidence(marker="FAILED one"),),
            ),
            make_verification_result(
                status=FAIL,
                exit_code=3,
                evidence=(make_evidence(marker="FAILED two"),),
            ),
            make_verification_result(
                status=FAIL,
                exit_code=4,
                evidence=(make_evidence(marker="FAILED three"),),
            ),
        ]
    )

    engine = build_engine(
        worker,
        build_full_pipeline(verify),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.terminal_failure is True

    assert result.success is False

    assert result.failure_stage == FAILURE_VERIFICATION

    assert result.attempts_used == 3

    assert worker.calls == 3

    assert all(
        attempt.status == AttemptStatus.FAILED
        for attempt in result.attempt_history
    )


def test_f3_fingerprint_exception_is_terminal_no_retry(tmp_path):

    target = make_target(tmp_path)

    def exploding_producer(content):

        patch = ExplodingPatch(
            path=str(target),
            action="modify",
            reason="Fingerprint boom.",
            old_content=content,
            new_content=content + "\n# exploded\n",
            allowed_paths=(str(target),),
        )

        return make_worker_result(patch)

    worker = FakeRecoveryWorker(
        target,
        [exploding_producer],
    )

    verify = FakeVerificationExecutor(
        [
            make_verification_result(),
        ]
    )

    engine = build_engine(
        worker,
        build_full_pipeline(verify),
    )

    result = engine.execute(
        None,
        "recover"
    )

    assert result.terminal_failure is True

    assert result.success is False

    assert worker.calls == 1

    assert result.attempts_used == 1

    assert result.retry_count == 0

    assert result.max_attempts == 3

    assert result.failure_stage == FAILURE_UNEXPECTED

    assert len(verify.calls) == 0

    assert (
        result.attempt_history[0].status
        == AttemptStatus.ERROR
    )

    assert (
        result.attempt_history[0].failure_stage
        == FAILURE_UNEXPECTED
    )

    assert (
        "Fingerprint exception: fingerprint exploded"
        in result.failure_reason
    )

    assert (
        result.attempt_history[0].failure_reason
        == "fingerprint exception: fingerprint exploded"
    )


def test_f2_recovery_assembly_enables_recovery_through_runtime(
    tmp_path
):

    target = make_target(tmp_path)

    worker_executor = WorkerExecutor(
        worker=WorkerAgent(
            analyzer=FakeWorkerAnalyzer()
        ),
        allowed_paths=(str(target),),
    )

    verify = FakeVerificationExecutor(
        [
            make_verification_result(),
        ]
    )

    kernel = RecordingKernel()

    agent = build_recovery_agent(
        kernel,
        worker_executor=worker_executor,
        verification_executor=verify,
        provider=StubProvider(),
    )

    assert agent.worker_pipeline is not None

    assert agent.recovery_engine is not None

    result = agent.chat(
        "worker: add worker proposal marker"
    )

    assert isinstance(result, RecoveryResult)

    assert result.success is True

    assert result.attempts_used == 1

    assert result.retry_count == 0

    assert result.final_apply_success is True

    assert result.final_verification_passed is True

    content = target.read_text(
        encoding="utf-8"
    )

    assert (
        "Fake worker proposal marker"
        in content
    )
