from simulation.context.context_builder import ContextBuilder
from simulation.core.event import Event
from simulation.llm.models import (
    Message,
    LLMRequest
)
from simulation.llm.provider_factory import ProviderFactory
from simulation.loop.loop_engine import LoopEngine


class Agent:

    def __init__(self, kernel):

        self.kernel = kernel

        self.provider = ProviderFactory.create()

        self.context_builder = ContextBuilder()

        self.loop = LoopEngine()

    def chat(self, prompt):

        self.loop.start(prompt)

        # Kullanıcının sorusunu Event Store'a kaydet
        self.kernel.dispatch(

            Event(

                event_type="UserQuestionReceived",

                payload={

                    "prompt": prompt

                }

            )

        )

        # Güncel context'i oluştur
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

        # AI cevabını Event olarak kaydet
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