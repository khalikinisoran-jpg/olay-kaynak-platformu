import pytest

from simulation.agent.agent import Agent
from simulation.agent.executors.llm_executor import LLMExecutor
from simulation.agent.strategy_dispatcher import StrategyDispatcher
from simulation.agent.worker.llm_code_analyzer import LLMCodeAnalyzer


class RecordingKernel:

    def __init__(self):

        self.events = []

        self.decision_trace = None

    def dispatch(self, event):

        self.events.append(event)

    def get_decision_trace(self):

        return self.decision_trace


def explode():

    raise AssertionError(
        "Provider must not be created without a real "
        "LLM call."
    )


def test_runtime_construction_does_not_require_api_key(
    monkeypatch
):

    monkeypatch.setattr(
        "simulation.llm.provider_factory.ProviderFactory.create",
        explode,
    )

    dispatcher = StrategyDispatcher()

    assert dispatcher.registry.exists("llm")

    agent = Agent(
        RecordingKernel(),
        dispatcher=dispatcher,
    )

    assert agent.worker_pipeline is None

    executor = LLMExecutor()

    assert executor is not None


def test_provider_creation_is_explicit_and_fail_closed(
    monkeypatch
):

    monkeypatch.setattr(
        "simulation.llm.provider_factory.ProviderFactory.create",
        explode,
    )

    agent = Agent(
        RecordingKernel(),
        provider=None,
    )

    with pytest.raises(AssertionError):

        agent.provider

    analyzer = LLMCodeAnalyzer()

    with pytest.raises(AssertionError):

        analyzer._get_provider()


def test_memory_store_strategy_runs_without_provider(
    monkeypatch,
    tmp_path,
):

    monkeypatch.setattr(
        "simulation.llm.provider_factory.ProviderFactory.create",
        explode,
    )

    kernel = RecordingKernel()

    agent = Agent(
        kernel,
        provider=None,
    )

    response = agent.chat("benim adım Ahmet")

    assert isinstance(response, str)

    assert "Ahmet" in response

    assert any(
        event.event_type == "MemoryStored"
        for event in kernel.events
    )
