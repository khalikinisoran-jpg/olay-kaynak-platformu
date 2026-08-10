from simulation.agent.agent import (
    Agent
)

from simulation.agent.apply.apply_executor import (
    ApplyExecutor
)

from simulation.agent.controller.controller import (
    Controller
)

from simulation.agent.executors.worker.worker_executor import (
    WorkerExecutor
)

from simulation.agent.pipeline.apply_verify_pipeline import (
    ApplyVerifyPipeline
)

from simulation.agent.pipeline.worker_action_pipeline import (
    WorkerActionPipeline,
    WorkerPipelineResult,
)

from simulation.agent.strategy_dispatcher import (
    StrategyDispatcher
)

from simulation.agent.verify.verification_result import (
    FAIL,
    PASS,
    VerificationEvidence,
    VerificationResult,
)

from simulation.agent.worker.patch_validator import (
    PatchValidator
)

from simulation.agent.worker.worker_agent import (
    WorkerAgent
)

from tests.fake_worker_analyzer import (
    FakeWorkerAnalyzer
)


class RecordingKernel:

    def __init__(self):

        self.events = []

    def dispatch(self, event):

        self.events.append(event)


class StubProvider:

    def chat(self, request):

        raise AssertionError(
            "No real LLM call expected during "
            "the worker runtime integration test."
        )

    def get_model_name(self):

        return "stub"


class FakeVerificationExecutor:

    def __init__(self, result):

        self.result = result

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

        return self.result


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


def build_agent(
    kernel,
    worker_executor,
    verification_result
):

    worker_pipeline = WorkerActionPipeline(
        patch_validator=PatchValidator(),
        controller=Controller(),
        apply_verify_pipeline=ApplyVerifyPipeline(
            apply_executor=ApplyExecutor(),
            verification_executor=FakeVerificationExecutor(
                verification_result
            ),
        ),
    )

    dispatcher = StrategyDispatcher(
        worker_executor=worker_executor
    )

    return Agent(
        kernel,
        dispatcher=dispatcher,
        provider=StubProvider(),
        worker_pipeline=worker_pipeline,
    )


def test_agent_chat_runs_full_worker_action_pipeline_pass(
    tmp_path
):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    worker_executor = WorkerExecutor(
        worker=WorkerAgent(
            analyzer=FakeWorkerAnalyzer()
        ),
        allowed_paths=(str(target),),
    )

    evidence = (
        VerificationEvidence(
            stage="tests",
            command=(
                "venv-python",
                "-m",
                "pytest",
                "-q",
            ),
            exit_code=0,
            stdout="1 passed",
            stderr="",
        ),
    )

    verification = make_verification_result(
        status=PASS,
        exit_code=0,
        stdout="1 passed",
        evidence=evidence,
    )

    kernel = RecordingKernel()

    agent = build_agent(
        kernel,
        worker_executor,
        verification,
    )

    result = agent.chat(
        "worker: add worker proposal marker"
    )

    assert isinstance(
        result,
        WorkerPipelineResult
    )

    assert result.success is True

    assert result.apply_success is True

    assert result.verification_passed is True

    assert result.verification_ran is True

    assert result.exit_code == 0

    assert result.evidence == evidence

    assert result.worker_result.success is True

    assert result.worker_result.patches

    assert (
        result.worker_result.patches[0].path
        == str(target)
    )

    content = target.read_text(
        encoding="utf-8"
    )

    assert (
        "Fake worker proposal marker"
        in content
    )

    assert content.startswith(original)

    event_types = [
        event.event_type
        for event in kernel.events
    ]

    assert "UserQuestionReceived" in event_types

    assert "AIResponseReceived" not in event_types


def test_agent_chat_reports_verification_failure_with_evidence(
    tmp_path
):

    target = tmp_path / "sample.py"

    original = "value = 1\n"

    target.write_text(
        original,
        encoding="utf-8"
    )

    worker_executor = WorkerExecutor(
        worker=WorkerAgent(
            analyzer=FakeWorkerAnalyzer()
        ),
        allowed_paths=(str(target),),
    )

    evidence = (
        VerificationEvidence(
            stage="tests",
            command=(
                "venv-python",
                "-m",
                "pytest",
                "-q",
            ),
            exit_code=2,
            stdout="1 failed",
            stderr="FAILED sample_test::test_x",
        ),
    )

    verification = make_verification_result(
        status=FAIL,
        exit_code=2,
        stdout="1 failed",
        stderr="FAILED sample_test::test_x",
        evidence=evidence,
        failure_reason=(
            "Test execution verification returned "
            "non-zero exit code 2."
        ),
    )

    kernel = RecordingKernel()

    agent = build_agent(
        kernel,
        worker_executor,
        verification,
    )

    result = agent.chat(
        "worker: add worker proposal marker"
    )

    assert result.success is False

    assert result.apply_success is True

    assert result.verification_passed is False

    assert result.verification_ran is True

    assert result.exit_code == 2

    assert result.stdout == "1 failed"

    assert result.stderr == (
        "FAILED sample_test::test_x"
    )

    assert result.evidence == evidence

    assert (
        "non-zero exit code 2"
        in result.failure_reason
    )

    content = target.read_text(
        encoding="utf-8"
    )

    assert (
        "Fake worker proposal marker"
        in content
    )


def test_agent_chat_multiple_proposals_apply_in_worker_order(
    tmp_path
):

    target_a = tmp_path / "alpha.py"

    target_b = tmp_path / "beta.py"

    original_a = "alpha = 1\n"

    original_b = "beta = 1\n"

    target_a.write_text(
        original_a,
        encoding="utf-8"
    )

    target_b.write_text(
        original_b,
        encoding="utf-8"
    )

    worker_executor = WorkerExecutor(
        worker=WorkerAgent(
            analyzer=FakeWorkerAnalyzer()
        ),
        allowed_paths=(
            str(target_a),
            str(target_b),
        ),
    )

    kernel = RecordingKernel()

    agent = build_agent(
        kernel,
        worker_executor,
        make_verification_result(
            status=PASS,
            exit_code=0,
            stdout="2 passed",
        ),
    )

    result = agent.chat(
        "worker: add marker to both files"
    )

    assert result.success is True

    assert result.verification_ran is True

    assert len(result.worker_result.patches) == 2

    assert (
        result.worker_result.patches[0].path
        == str(target_a)
    )

    assert (
        result.worker_result.patches[1].path
        == str(target_b)
    )

    assert len(result.patch_results) == 2

    assert all(
        stage.stage == "apply_verify"
        for stage in result.patch_results
    )

    assert all(
        stage.success
        for stage in result.patch_results
    )

    content_a = target_a.read_text(
        encoding="utf-8"
    )

    content_b = target_b.read_text(
        encoding="utf-8"
    )

    assert content_a.startswith(original_a)

    assert content_b.startswith(original_b)

    assert (
        "Fake worker proposal marker"
        in content_a
    )

    assert (
        "Fake worker proposal marker"
        in content_b
    )


def test_agent_chat_fails_closed_when_worker_cannot_propose(
    tmp_path
):

    missing = tmp_path / "missing.py"

    worker_executor = WorkerExecutor(
        worker=WorkerAgent(
            analyzer=FakeWorkerAnalyzer()
        ),
        allowed_paths=(str(missing),),
    )

    kernel = RecordingKernel()

    agent = build_agent(
        kernel,
        worker_executor,
        make_verification_result(),
    )

    result = agent.chat(
        "worker: inspect a missing file"
    )

    assert isinstance(
        result,
        WorkerPipelineResult
    )

    assert result.success is False

    assert result.verification_ran is False

    assert result.exit_code == -1

    assert (
        result.failure_reason
        == "Worker produced no patch proposals."
    )

    assert result.patch_results == ()

    assert (
        missing.exists() is False
    )
