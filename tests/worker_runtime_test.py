from simulation.agent.agent import Agent
from simulation.agent.executors.worker.worker_executor import (
    WorkerExecutor,
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


def make_dispatcher():

    executor = WorkerExecutor(
        worker=WorkerAgent(
            analyzer=FakeWorkerAnalyzer()
        )
    )

    recorder = RecordingWorkerExecutor(
        executor
    )

    dispatcher = StrategyDispatcher(
        worker_executor=recorder
    )

    return dispatcher, recorder


def test_planner_produces_worker_strategy_for_worker_prefix():

    planner = Planner()

    plan = planner.plan(
        "worker: add worker proposal marker"
    )

    assert plan["strategy"] == "worker"

    assert plan["steps"] == [
        "execute_worker"
    ]


def test_worker_strategy_registered_in_dispatcher():

    dispatcher, _ = make_dispatcher()

    assert dispatcher.registry.exists("worker") is True


def test_worker_strategy_dispatch_calls_worker_executor():

    dispatcher, recorder = make_dispatcher()

    result = dispatcher.dispatch(
        "worker",
        None,
        "worker: inspect worker contract"
    )

    assert recorder.calls == 1

    assert isinstance(result, WorkerResult)

    assert result.success is True


def test_agent_chat_worker_returns_worker_result_to_upper_flow():

    dispatcher, recorder = make_dispatcher()

    kernel = RecordingKernel()

    agent = Agent(
        kernel,
        dispatcher=dispatcher,
        provider=StubProvider()
    )

    result = agent.chat(
        "worker: add worker proposal marker"
    )

    assert recorder.calls == 1

    assert isinstance(result, WorkerResult)

    assert result.success is True

    assert result.task_id == "worker-task"

    assert result.patches

    assert (
        "Worker inspection and patch proposal "
        "completed."
        in result.summary
    )

    event_types = [
        event.event_type
        for event in kernel.events
    ]

    assert "UserQuestionReceived" in event_types

    assert "AIResponseReceived" not in event_types
