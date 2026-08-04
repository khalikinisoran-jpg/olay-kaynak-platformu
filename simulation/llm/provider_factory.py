from simulation.llm.openrouter_provider import OpenRouterProvider


class ProviderFactory:

    @staticmethod
    def create():

        return OpenRouterProvider()