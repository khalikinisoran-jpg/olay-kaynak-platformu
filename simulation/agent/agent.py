from simulation.context.context_builder import ContextBuilder
from simulation.core.event import Event

from simulation.llm.models import (
    Message,
    LLMRequest
)

from simulation.llm.provider_factory import ProviderFactory

from simulation.loop.loop_engine import LoopEngine

from simulation.planner.planner import Planner
from simulation.services.tool_executor import ToolExecutor


class Agent:

    def __init__(self, kernel):

        self.kernel = kernel

        self.provider = ProviderFactory.create()

        self.context_builder = ContextBuilder()

        self.loop = LoopEngine()

        self.planner = Planner()

        self.tool_executor = ToolExecutor()

    def chat(self, prompt):

        self.loop.start(prompt)

        # User Event
        self.kernel.dispatch(

            Event(

                event_type="UserQuestionReceived",

                payload={

                    "prompt": prompt

                }

            )

        )

        plan = self.planner.plan(prompt)

        if plan["strategy"] == "calculator":

            tool_result = self.tool_executor.execute(

                "calculator",

                prompt

            )

            class ToolResponse:

                def __init__(self, result):

                    self.content = result["output"]

                    self.model = result["tool"]

                    self.tokens_used = 0

            response = ToolResponse(
                tool_result
            )

        else:

            context = self.context_builder.build(
                self.kernel
            )

            request = LLMRequest(

                messages=[

                    Message(

                        role="system",

                        content=context

                    ),

                    Message(

                        role="user",

                        content=prompt

                    )

                ]

            )

            response = self.provider.chat(
                request
            )

        # AI Event
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