from simulation.tools.registry import ToolRegistry


class ToolExecutor:

    def __init__(self):

        self.registry = ToolRegistry()

    def execute(
        self,
        strategy,
        user_input
    ):

        tool = self.registry.get(
            strategy
        )

        if tool is None:

            return {

                "success": False,

                "tool": strategy,

                "output": "Tool not found."

            }

        return tool.execute(
            user_input
        )