from simulation.agent.executors.calculator_executor import CalculatorExecutor
from simulation.agent.executors.llm_executor import LLMExecutor
from simulation.agent.executors.memory_store_executor import MemoryStoreExecutor
from simulation.agent.executors.memory_recall_executor import MemoryRecallExecutor


class ExecutorRegistry:
    """
    Central registry for executor instances.
    """

    def __init__(self):

        self._executors = {

            "calculator": CalculatorExecutor(),

            "llm": LLMExecutor(),

            "memory_store": MemoryStoreExecutor(),

            "memory_recall": MemoryRecallExecutor(),

        }

    def register(self, strategy, executor):

        self._executors[strategy] = executor

    def get(self, strategy):

        return self._executors.get(strategy)

    def exists(self, strategy):

        return strategy in self._executors

    def strategies(self):

        return sorted(self._executors.keys())