from simulation.tools.calculator import Calculator


calculator = Calculator()

tests = [

    "15 + 27",

    "100 / 4",

    "8 * 9",

    "9 - 5",

    "5.5 + 2.5",

    "10 / 0",

    "abc"

]

for expression in tests:

    result = calculator.execute(
        expression
    )

    print()

    print("--------------------------------")

    print(expression)

    print(result)