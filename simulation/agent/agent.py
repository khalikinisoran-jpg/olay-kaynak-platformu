from simulation.core.event import Event

from simulation.loop.loop_engine import LoopEngine
from simulation.planner.planner import Planner

from simulation.agent.executors.calculator_executor import CalculatorExecutor
from simulation.agent.executors.memory_executor import MemoryExecutor
from simulation.agent.executors.llm_executor import LLMExecutor


class Agent:

    def __init__(self, kernel):

        self.kernel = kernel

        self.loop = LoopEngine()

        self.planner = Planner()

        self.calculator = CalculatorExecutor()

        self.memory = MemoryExecutor()

        self.llm = LLMExecutor()

    def chat(
        self,
        prompt
    ):

        self.loop.start(prompt)

        self.kernel.dispatch(

            Event(

                event_type="UserQuestionReceived",

                payload={

                    "prompt": prompt

                }

            )

        )

        plan = self.planner.plan(prompt)

        strategy = plan["strategy"]

        # ------------------------------------
        # Calculator
        # ------------------------------------

        if strategy == "calculator":

            response = self.calculator.execute(

                self,

                prompt

            )

        # ------------------------------------
        # Memory Store
        # ------------------------------------

        elif strategy == "memory_store":

            response = self.memory.execute(

                self,

                prompt

            )

        # ------------------------------------
        # Memory Recall
        # ------------------------------------

        elif strategy == "memory_recall":

            name = self.kernel.state.memory.get(

                "user.name"

            )

            class Response:

                def __init__(

                    self,

                    name

                ):

                    if name:

                        self.content = f"Adın {name}."

                    else:

                        self.content = "Henüz ismini bilmiyorum."

                    self.model = "memory"

                    self.tokens_used = 0

            response = Response(name)

        # ------------------------------------
        # LLM
        # ------------------------------------

        else:

            response = self.llm.execute(

                self,

                prompt

            )

        self.kernel.dispatch(

            Event(

                event_type="AIResponseReceived",

                payload={

                    "prompt": prompt,

                    "response": response.content,

                    "model": response.model,

                    "tokens": response.tokens_used

                }

            )

        )

        self.loop.verifying()

        self.loop.complete()

        return response.content