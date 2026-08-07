from simulation.planner.planner import Planner

planner = Planner()

tests = [

    "15 + 27",

    "Bugün hava nasıl?",

    "Benim adım Ahmet",

    "Benim adım ne?",

    "Merhaba"

]

for text in tests:

    plan = planner.plan(text)

    print()

    print("--------------------------------")

    print(text)

    print(plan)