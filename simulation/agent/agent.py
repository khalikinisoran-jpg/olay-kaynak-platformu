from simulation.llm.provider_factory import ProviderFactory
from simulation.llm.models import (
    Message,
    LLMRequest
)

from simulation.core.event import Event


class Agent:

    def __init__(self, kernel):

        self.kernel = kernel
        self.provider = ProviderFactory.create()

    def ask(self, prompt):

        request = LLMRequest(
            messages=[
                Message(
                    role="user",
                    content=prompt
                )
            ]
        )

        response = self.provider.chat(request)

        event = Event(
            event_type="AIResponseReceived",
            payload={
                "prompt": prompt,
                "response": response.content,
                "model": response.model,
                "tokens": response.tokens_used
            }
        )

        self.kernel.dispatch(event)

        return response.content