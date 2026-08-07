from simulation.agent.strategy_dispatcher import StrategyDispatcher

dispatcher = StrategyDispatcher()


def calculator():

    return "calculator"


def memory():

    return "memory"


callbacks = {

    "calculator": calculator,

    "memory": memory

}


print()

print("------------------------------")

print(

    dispatcher.dispatch(

        "calculator",

        callbacks

    )

)

print(

    dispatcher.dispatch(

        "memory",

        callbacks

    )

)