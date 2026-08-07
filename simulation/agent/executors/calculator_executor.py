from simulation.services.tool_executor import ToolExecutor


class CalculatorExecutor:

    def __init__(self):

        self.tool_executor = ToolExecutor()

    def execute(
        self,
        agent,
        prompt
    ):

        result = self.tool_executor.execute(
            "calculator",
            prompt
        )

        class Response:

            def __init__(self, result):

                self.content = result["output"]

                self.model = result["tool"]

                self.tokens_used = 0

        return Response(result)