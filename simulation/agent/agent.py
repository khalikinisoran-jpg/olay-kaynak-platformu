from simulation.context.context_builder import ContextBuilder
from simulation.core.event import Event

from simulation.llm.provider_factory import ProviderFactory

from simulation.loop.loop_engine import LoopEngine

from simulation.planner.planner import Planner

from simulation.agent.strategy_dispatcher import StrategyDispatcher

from simulation.agent.worker.worker_result import WorkerResult


class Agent:

    def __init__(self, kernel, dispatcher=None, provider=None):

        self.kernel = kernel

        self.provider = (
            provider
            if provider is not None
            else ProviderFactory.create()
        )

        self.context_builder = ContextBuilder()

        self.loop = LoopEngine()

        self.planner = Planner()

        self.dispatcher = (
            dispatcher
            if dispatcher is not None
            else StrategyDispatcher()
        )

    def chat(self, prompt):

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

        response = self.dispatcher.dispatch(

            plan["strategy"],

            self,

            prompt

        )

        if isinstance(response, WorkerResult):

            self.loop.verifying()

            self.loop.complete()

            return response

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