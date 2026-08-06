from abc import ABC, abstractmethod


class BaseTool(ABC):

    @abstractmethod
    def execute(
        self,
        user_input
    ):
        pass