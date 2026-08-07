from simulation.context.context_builder import ContextBuilder

from simulation.llm.models import (
    Message,
    LLMRequest
)

from simulation.llm.provider_factory import ProviderFactory


class LLMExecutor:

    def __init__(self):

        self.provider = ProviderFactory.create()

        self.context_builder = ContextBuilder()

    def execute(
        self,
        agent,
        prompt
    ):

        context = self.context_builder.build(
            agent.kernel
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

        return self.provider.chat(
            request
        )