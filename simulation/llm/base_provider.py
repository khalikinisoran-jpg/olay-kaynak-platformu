from abc import ABC, abstractmethod

from simulation.llm.models import (
    LLMRequest,
    LLMResponse
)


class ProviderError(Exception):
    pass


class BaseProvider(ABC):

    @abstractmethod
    def chat(
        self,
        request: LLMRequest
    ) -> LLMResponse:
        pass

    @abstractmethod
    def get_model_name(
        self
    ) -> str:
        pass