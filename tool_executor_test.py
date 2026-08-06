from simulation.services.tool_executor import ToolExecutor


executor = ToolExecutor()


tests = [

    ("calculator", "15 + 27"),

    ("calculator", "100 / 4"),

    ("calculator", "10 / 0"),

    ("calculator", "abc"),

    ("weather", "İstanbul")

]


for strategy, text in tests:

    result = executor.execute(

        strategy,

        text

    )

    print()

    print("--------------------------------")

    print(strategy)

    print(text)

    print(result)