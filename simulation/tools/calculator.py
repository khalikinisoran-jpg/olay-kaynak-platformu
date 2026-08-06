import operator
import re


class Calculator:

    OPERATORS = {

        "+": operator.add,

        "-": operator.sub,

        "*": operator.mul,

        "/": operator.truediv

    }

    def execute(
        self,
        expression: str
    ):

        expression = expression.strip()

        match = re.fullmatch(

            r"(-?\d+(?:\.\d+)?)\s*([\+\-\*/])\s*(-?\d+(?:\.\d+)?)",

            expression

        )

        if match is None:

            return {

                "success": False,

                "tool": "calculator",

                "output": "Unsupported expression."

            }

        left = float(
            match.group(1)
        )

        operator_symbol = match.group(2)

        right = float(
            match.group(3)
        )

        try:

            result = self.OPERATORS[
                operator_symbol
            ](
                left,
                right
            )

        except ZeroDivisionError:

            return {

                "success": False,

                "tool": "calculator",

                "output": "Division by zero."

            }

        if result.is_integer():

            result = int(result)

        return {

            "success": True,

            "tool": "calculator",

            "output": str(result)

        }