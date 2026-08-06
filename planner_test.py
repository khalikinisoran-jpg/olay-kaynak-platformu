from simulation.planner.planner import Planner


planner = Planner()

tests = [

    "15 + 27",

    "Bugün hava nasıl?",

    "Merhaba"

]

for text in tests:

    plan = planner.create_plan(text)

    print()

    print("--------------------------------")

    print(text)

    print(plan)