from simulation.agent.agent import Agent
from simulation.agent.executors.worker.worker_executor import (
    WorkerExecutor,
)
from simulation.agent.pipeline.worker_action_pipeline import (
    WorkerPipelineResult,
)
from simulation.agent.strategy_dispatcher import StrategyDispatcher
from simulation.agent.worker.worker_agent import WorkerAgent
from simulation.agent.worker.worker_result import WorkerResult
from simulation.planner.planner import Planner

from tests.fake_worker_analyzer import FakeWorkerAnalyzer


class RecordingKernel:

    def __init__(self):

        self.events = []

    def dispatch(self, event):

        self.events.append(event)


class StubProvider:

    def chat(self, request):

        raise AssertionError(
            "No real LLM call expected during "
            "the worker runtime test."
        )

    def get_model_name(self):

        return "stub"


class RecordingWorkerExecutor:

    def __init__(self, executor):

        self.executor = executor

        self.calls = 0

    def execute(self, agent, prompt):

        self.calls += 1

        return self.executor.execute(
            agent,
            prompt
        )


class RecordingWorkerPipeline:

    def __init__(self):

        self.worker_results = []

    def execute(self, worker_result):

        self.worker_results.append(worker_result)

        return WorkerPipelineResult(
            success=worker_result.success,
            worker_result=worker_result,
            failure_reason=(
                ""
                if worker_result.success
                else worker_result.summary
            ),
            exit_code=(
                0
                if worker_result.success
                else -1
            ),
        )


def make_dispatcher(allowed_paths):

    executor = WorkerExecutor(
        worker=WorkerAgent(
            analyzer=FakeWorkerAnalyzer()
        ),
        allowed_paths=tuple(allowed_paths),
    )

    recorder = RecordingWorkerExecutor(
        executor
    )

    dispatcher = StrategyDispatcher(
        worker_executor=recorder
    )

    return dispatcher, recorder


def make_target(tmp_path):

    target = tmp_path / "sample.py"

    target.write_text(
        "value = 1\n",
        encoding="utf-8"
    )

    return target


def test_planner_produces_worker_strategy_for_worker_prefix():

    planner = Planner()

    plan = planner.plan(
        "worker: add worker proposal marker"
    )

    assert plan["strategy"] == "worker"

    assert plan["steps"] == [
        "execute_worker"
    ]


def test_worker_strategy_registered_in_dispatcher(
    tmp_path
):

    target = make_target(tmp_path)

    dispatcher, _ = make_dispatcher(
        (str(target),)
    )

    assert dispatcher.registry.exists("worker") is True


def test_worker_strategy_dispatch_calls_worker_executor(
    tmp_path
):

    target = make_target(tmp_path)

    dispatcher, recorder = make_dispatcher(
        (str(target),)
    )

    result = dispatcher.dispatch(
        "worker",
        None,
        "worker: inspect worker contract"
    )

    assert recorder.calls == 1

    assert isinstance(result, WorkerResult)

    assert result.success is True


def test_agent_chat_worker_returns_final_pipeline_result_to_upper_flow(
    tmp_path
):

    target = make_target(tmp_path)

    dispatcher, recorder = make_dispatcher(
        (str(target),)
    )

    kernel = RecordingKernel()

    pipeline = RecordingWorkerPipeline()

    agent = Agent(
        kernel,
        dispatcher=dispatcher,
        provider=StubProvider(),
        worker_pipeline=pipeline,
    )

    result = agent.chat(
        "worker: add worker proposal marker"
    )

    assert recorder.calls == 1

    assert isinstance(result, WorkerPipelineResult)

    assert result.success is True

    assert result.worker_result.task_id == "worker-task"

    assert result.worker_result.patches

    assert (
        "Worker inspection and patch proposal "
        "completed."
        in result.worker_result.summary
    )

    assert len(pipeline.worker_results) == 1

    worker_result = pipeline.worker_results[0]

    assert isinstance(
        worker_result,
        WorkerResult
    )

    assert worker_result.success is True

    event_types = [
        event.event_type
        for event in kernel.events
    ]

    assert "UserQuestionReceived" in event_types

    assert "AIResponseReceived" not in event_types


def test_default_agent_does_not_construct_action_pipeline():

    kernel = RecordingKernel()

    agent = Agent(
        kernel,
        provider=StubProvider(),
    )

    assert agent.worker_pipeline is None


def test_worker_executor_default_allowed_paths_are_fail_closed():

    executor = WorkerExecutor(
        worker=WorkerAgent(
            analyzer=FakeWorkerAnalyzer()
        )
    )

    assert executor.allowed_paths == ()

    result = executor.execute(
        None,
        "worker: add worker proposal marker"
    )

    assert result.success is False

    assert result.patches == ()

    assert (
        "No allowed paths"
        in result.summary
    )


def test_default_agent_runtime_is_proposal_only_no_apply_no_verify(
    tmp_path
):

    target = make_target(tmp_path)

    original = target.read_text(
        encoding="utf-8"
    )

    dispatcher, recorder = make_dispatcher(
        (str(target),)
    )

    kernel = RecordingKernel()

    agent = Agent(
        kernel,
        dispatcher=dispatcher,
        provider=StubProvider(),
    )

    assert agent.worker_pipeline is None

    result = agent.chat(
        "worker: add worker proposal marker"
    )

    assert recorder.calls == 1

    assert isinstance(result, WorkerResult)

    assert result.success is True

    assert result.patches

    assert result.patches[0].path == str(target)

    assert (
        target.read_text(
            encoding="utf-8"
        )
        == original
    )

    event_types = [
        event.event_type
        for event in kernel.events
    ]

    assert "UserQuestionReceived" in event_types

    assert "AIResponseReceived" not in event_types
