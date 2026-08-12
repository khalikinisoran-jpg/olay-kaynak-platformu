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
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_policy import RiskPolicy


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
        "--governed",
        action="store_true",
        help=(
            "Enable the governed apply runtime: the bounded "
            "worker action pipeline PLUS deterministic risk "
            "classification and a store-backed, single-use "
            "human-approval authorization boundary "
            "(MISSION-011/012/014). LOW/MEDIUM risk proposals "
            "flow to apply+verify (with rollback on "
            "verification failure); HIGH/CRITICAL/UNKNOWN fail "
            "closed unless a valid approval exists in the "
            "approval ledger. Requires --allowed-path."
        ),
    )

    parser.add_argument(
        "--allowed-path",
        action="append",
        default=[],
        help=(
            "Path the worker may read/inspect/propose and, "
            "with --recovery or --governed, apply patches to. "
            "Repeatable. Empty by default (fail-closed: no "
            "mutations)."
        ),
    )

    parser.add_argument(
        "--approval-ledger",
        default="data/approval_ledger.jsonl",
        help=(
            "Durable approval ledger path used by --governed. "
            "Grants and consumption survive process restarts; "
            "a corrupted ledger fails closed at startup."
        ),
    )

    args = parser.parse_args()

    print("=" * 50)
    print(" Event-Sourced AI Runtime")
    print("=" * 50)

    if args.governed and not args.allowed_path:

        parser.error(
            "--governed requires at least one --allowed-path "
            "(fail-closed: no mutation scope)."
        )

    kernel = Kernel(
        EventStore()
    )

    if args.governed:

        agent = build_recovery_agent(
            kernel,
            worker_executor=WorkerExecutor(
                allowed_paths=tuple(args.allowed_path),
            ),
            risk_engine=RiskEngine(),
            risk_policy=RiskPolicy(),
            approval_ledger_path=args.approval_ledger,
        )

        print(
            "\n[governed mode] apply+verify+recovery active, "
            "risk-classified, approval store-backed."
        )

        print(
            f"[governed mode] approval ledger: {args.approval_ledger}"
        )

        print(
            "[governed mode] HIGH/CRITICAL proposals require a "
            "valid human approval and fail closed otherwise."
        )

    elif args.recovery:

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
