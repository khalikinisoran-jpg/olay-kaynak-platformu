import argparse

from simulation.agent.agent import Agent
from simulation.agent.executors.worker.worker_executor import (
    WorkerExecutor
)
from simulation.agent.recovery.recovery_assembly import (
    build_recovery_agent
)
from simulation.core.kernel import Kernel
from simulation.persistence.event_store import EventStore


def main():

    parser = argparse.ArgumentParser(
        description="Event-Sourced AI Runtime"
    )

    parser.add_argument(
        "--recovery",
        action="store_true",
        help=(
            "Enable the bounded worker action pipeline "
            "(apply + verification + bounded recovery). "
            "Off by default: the default runtime stays "
            "proposal-only and never mutates files."
        ),
    )

    parser.add_argument(
        "--allowed-path",
        action="append",
        default=[],
        help=(
            "Path the worker may read/inspect/propose and, "
            "with --recovery, apply patches to. Repeatable. "
            "Empty by default (fail-closed: no mutations)."
        ),
    )

    args = parser.parse_args()

    print("=" * 50)
    print(" Event-Sourced AI Runtime")
    print("=" * 50)

    kernel = Kernel(
        EventStore()
    )

    if args.recovery:

        agent = build_recovery_agent(
            kernel,
            worker_executor=WorkerExecutor(
                allowed_paths=tuple(args.allowed_path),
            ),
        )

    else:

        agent = Agent(kernel)

    while True:

        message = input("\nSen > ")

        if message.lower() in [
            "exit",
            "quit"
        ]:
            print("\nÇıkılıyor...")
            break

        response = agent.chat(message)

        print("\nAgent >", response)

        print(
            "\nToplam Event :",
            kernel.event_count()
        )


if __name__ == "__main__":

    main()
