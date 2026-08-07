from simulation.agent.registry.executor_registry import ExecutorRegistry

from simulation.agent.executors.calculator_executor import CalculatorExecutor
from simulation.agent.executors.memory_store_executor import MemoryStoreExecutor
from simulation.agent.executors.memory_recall_executor import MemoryRecallExecutor
from simulation.agent.executors.llm_executor import LLMExecutor


class StrategyDispatcher:

    def __init__(self):

        self.registry = ExecutorRegistry()

        self.registry.register(
            "calculator",
            CalculatorExecutor()
        )

        self.registry.register(
            "memory_store",
            MemoryStoreExecutor()
        )

        self.registry.register(
            "memory_recall",
            MemoryRecallExecutor()
        )

        self.registry.register(
            "llm",
            LLMExecutor()
        )

    def dispatch(
        self,
        strategy,
        agent,
        prompt
    ):

        executor = self.registry.get(
            strategy
        )

        if executor is None:

            raise ValueError(
                f"Unknown strategy: {strategy}"
            )

        return executor.execute(
            agent,
            prompt
        )