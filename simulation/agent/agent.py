from simulation.context.context_builder import ContextBuilder
from simulation.core.event import Event
from simulation.llm.models import (
    Message,
    LLMRequest
)
from simulation.llm.provider_factory import ProviderFactory


class Agent:

    def __init__(self, kernel):

        self.kernel = kernel

        self.provider = ProviderFactory.create()

        self.context_builder = ContextBuilder()

    def chat(self, prompt):

        context = self.context_builder.build(
            self.kernel.get_state()
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

        event = Event(

            event_type="AIResponseReceived",

            payload={

                "prompt": prompt,

                "response": response.content,

                "model": response.model,

                "tokens": response.tokens_used

            }

        )

        self.kernel.dispatch(
            event
        )

        return response.content