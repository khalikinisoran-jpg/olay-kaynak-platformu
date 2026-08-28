from simulation.context.context_builder import ContextBuilder

from simulation.llm.models import (
    Message,
    LLMRequest
)

from simulation.llm.provider_factory import ProviderFactory


class LLMExecutor:

    def __init__(self):

        self._resolved_provider = None

        self.context_builder = ContextBuilder()

    def _get_provider(self):

        if self._resolved_provider is None:

            self._resolved_provider = ProviderFactory.create()

        return self._resolved_provider

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

        return self._get_provider().chat(
            request
        )
