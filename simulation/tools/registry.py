from simulation.tools.calculator import Calculator


class ToolRegistry:

    def __init__(self):

        self.tools = {

            Calculator.NAME: Calculator()

        }

    def get(
        self,
        strategy
    ):

        return self.tools.get(
            strategy
        )

    def list_tools(self):

        result = []

        for tool in self.tools.values():

            result.append({

                "name": tool.NAME,

                "description": tool.DESCRIPTION,

                "version": tool.VERSION

            })

        return result

    def register(
        self,
        tool
    ):

        self.tools[tool.NAME] = tool