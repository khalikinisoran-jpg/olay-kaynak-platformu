from simulation.planner.planner import Planner
from simulation.agent.registry.executor_registry import ExecutorRegistry


def test_planner_strategy_executor_contract():

    planner = Planner()
    registry = ExecutorRegistry()

    test_cases = [
        ("15 + 27", "calculator"),
        ("Merhaba", "llm"),
        ("Benim adım Ahmet", "memory_store"),
        ("Benim adım ne?", "memory_recall"),
        ("worker: test worker task", "worker"),
    ]

    for prompt, expected_strategy in test_cases:

        plan = planner.plan(prompt)

        strategy = plan["strategy"]

        assert strategy == expected_strategy, (
            f"Planner returned '{strategy}' "
            f"instead of '{expected_strategy}'"
        )

        assert registry.exists(strategy), (
            f"No executor registered for '{strategy}'"
        )