from abc import ABC, abstractmethod


class BaseExecutor(ABC):

    @abstractmethod
    def execute(
        self,
        agent,
        prompt
    ):
        pass