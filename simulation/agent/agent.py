from simulation.core.event import Event
from simulation.llm.provider_factory import ProviderFactory
from simulation.llm.models import (
    Message,
    LLMRequest,
)


class Agent:

    def __init__(self, kernel):

        self.kernel = kernel

        self.provider = ProviderFactory.create()


    def chat(self, message: str):

        request = LLMRequest(

            messages=[

                Message(
                    role="system",
                    content="You are a helpful assistant."
                ),

                Message(
                    role="user",
                    content=message
                )
            ]
        )

        response = self.provider.chat(request)

        event = Event(

            event_type="AIResponseReceived",

            payload={

                "user_message": message,

                "response": response.content
            },

            sequence=self.kernel.event_count() + 1
        )

        self.kernel.dispatch(event)

        return response.content