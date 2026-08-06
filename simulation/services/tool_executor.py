from simulation.tools.calculator import Calculator


class ToolExecutor:

    def __init__(self):

        self.tools = {

            "calculator": Calculator()

        }

    def execute(
        self,
        strategy,
        user_input
    ):

        tool = self.tools.get(strategy)

        if tool is None:

            return {

                "success": False,

                "tool": strategy,

                "output": "Tool not found."

            }

        return tool.execute(
            user_input
        )