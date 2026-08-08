from simulation.agent.strategy_dispatcher import StrategyDispatcher


dispatcher = StrategyDispatcher()


assert dispatcher.registry.exists("calculator")
assert dispatcher.registry.exists("memory_store")
assert dispatcher.registry.exists("memory_recall")
assert dispatcher.registry.exists("llm")


response = dispatcher.dispatch(
    "calculator",
    None,
    "15 + 27"
)


assert response.content == "42"


print()
print("------------------------------")
print("Strategy Dispatcher Test Passed")
print("------------------------------")
print(
    "Registered strategies:",
    dispatcher.registry.strategies()
)