import argparse

from simulation.agent.agent import Agent
from simulation.agent.approval.approval_console import (
    ConsoleApprovalGateway
)
from simulation.agent.approval.approval_ledger import (
    ApprovalLedger
)
from simulation.agent.approval.approval_store import (
    ApprovalStore
)
from simulation.agent.apply.apply_outcome_journal import (
    ApplyOutcomeJournal
)
from simulation.agent.evidence.worker_evidence_recorder import (
    WorkerEvidenceRecorder
)
from simulation.agent.executors.worker.worker_executor import (
    WorkerExecutor
)
from simulation.agent.recovery.recovery_assembly import (
    build_recovery_agent,
    run_startup_reconciliation,
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
            "The authorization boundary stays ACTIVE: "
            "LOW/MEDIUM risk proposals auto-apply with "
            "rollback on verification failure, and "
            "HIGH/CRITICAL/UNKNOWN fail closed unless a valid "
            "approval exists in the approval ledger (pre-granted "
            "via the ledger; no interactive prompt). Off by "
            "default: the default runtime stays proposal-only "
            "and never mutates files."
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
            "Durable approval ledger path used by --recovery and "
            "--governed. Grants and consumption survive process "
            "restarts; a corrupted ledger fails closed at startup."
        ),
    )

    parser.add_argument(
        "--approval-ledger-anchor-path",
        default=None,
        help=(
            "MISSION-N1 trust anchor file for the approval ledger. "
            "Enables keyed HMAC chain-head anchoring so truncation / "
            "modification / forgery of the approval ledger fails "
            "closed at reload (a forged or replayed consumed approval "
            "cannot be resurrected). The key is the same CHAIN_ANCHOR_KEY "
            "environment variable or --anchor-key-path used by the event "
            "store anchor. Fail-closed: enabling this without a key "
            "refuses to start."
        ),
    )

    parser.add_argument(
        "--apply-journal",
        default="data/apply_journal.jsonl",
        help=(
            "Durable apply intent/outcome journal used by --recovery "
            "and --governed (MISSION-019). Records every apply intent "
            "and its terminal outcome so a crash between a file write "
            "and the evidence event is detectable after restart. A "
            "corrupted journal fails closed at startup. Never an "
            "authorization input."
        ),
    )

    parser.add_argument(
        "--anchor-path",
        default=None,
        help=(
            "MISSION-N trust anchor file for the event store. Enables "
            "keyed HMAC chain-head anchoring so tail deletion / tail "
            "edit / hash-recomputed middle deletion fail closed at "
            "recovery. The key is read from the CHAIN_ANCHOR_KEY "
            "environment variable or from --anchor-key-path. The key "
            "must NEVER be stored in the repository, snapshots or "
            "logs. Fail-closed: enabling the anchor without a key "
            "refuses to start."
        ),
    )

    parser.add_argument(
        "--anchor-key-path",
        default=None,
        help=(
            "Read the trust-anchor key from this file (operator "
            "managed, outside the repository). Mutually exclusive "
            "with CHAIN_ANCHOR_KEY; the key must be at least 32 bytes."
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

    if args.recovery and not args.allowed_path:

        parser.error(
            "--recovery requires at least one --allowed-path "
            "(fail-closed: no mutation scope)."
        )

    kernel = Kernel(
        EventStore(
            anchor_path=args.anchor_path,
            anchor_key_path=args.anchor_key_path,
        )
    )

    if args.anchor_path is None:

        print(
            "\n[event store] UNANCHORED: no --anchor-path given. "
            "Tail deletion / tail edit of the event log is NOT "
            "detected. For a security-sensitive deployment pass "
            "--anchor-path (key via CHAIN_ANCHOR_KEY or "
            "--anchor-key-path)."
        )

    else:

        print(
            "[event store] ANCHORED: event-log tail integrity is "
            "verified against the keyed chain-head trust anchor "
            "on every recovery."
        )

    if args.governed:

        risk_engine = RiskEngine()

        recorder = WorkerEvidenceRecorder(kernel=kernel)

        approval_store = ApprovalStore(
            evidence_recorder=recorder,
            ledger=ApprovalLedger(
                path=args.approval_ledger,
                anchor_path=(
                    args.approval_ledger_anchor_path
                ),
                anchor_key_path=args.anchor_key_path,
            ),
        )

        apply_journal = ApplyOutcomeJournal(
            path=args.apply_journal
        )

        _report_startup_reconciliation(
            apply_journal,
            args.allowed_path,
            approval_store,
        )

        approval_gateway = ConsoleApprovalGateway(
            store=approval_store,
            risk_engine=risk_engine,
            authorizer="human-operator",
            ttl_seconds=3600,
        )

        agent = build_recovery_agent(
            kernel,
            worker_executor=WorkerExecutor(
                allowed_paths=tuple(args.allowed_path),
            ),
            risk_engine=risk_engine,
            risk_policy=RiskPolicy(),
            approval_store=approval_store,
            approval_gateway=approval_gateway,
            evidence_recorder=recorder,
            apply_journal=apply_journal,
        )

        print(
            "\n[governed mode] apply+verify+recovery active, "
            "risk-classified, approval store-backed."
        )

        print(
            f"[governed mode] approval ledger: {args.approval_ledger}"
        )

        if args.approval_ledger_anchor_path is None:

            print(
                "\n[approval ledger] UNANCHORED: no "
                "--approval-ledger-anchor-path given. The ledger's "
                "unkeyed chain can be truncated/forged by a data-dir "
                "writer (a consumed approval could be resurrected). "
                "For a security-sensitive deployment pass "
                "--approval-ledger-anchor-path (key via "
                "CHAIN_ANCHOR_KEY or --anchor-key-path)."
            )

        else:

            print(
                "[approval ledger] ANCHORED: ledger tail integrity is "
                "verified against the keyed chain-head trust anchor "
                "on every reload."
            )

        print(
            f"[governed mode] apply journal: {args.apply_journal}"
        )

        print(
            "[governed mode] HIGH/CRITICAL proposals require a "
            "valid human approval and fail closed otherwise."
        )

        print(
            "[governed mode] approvals are granted interactively "
            "through the CLI when a HIGH/CRITICAL proposal arrives "
            "without a valid stored approval."
        )

    elif args.recovery:

        risk_engine = RiskEngine()

        recorder = WorkerEvidenceRecorder(kernel=kernel)

        approval_store = ApprovalStore(
            evidence_recorder=recorder,
            ledger=ApprovalLedger(
                path=args.approval_ledger,
                anchor_path=(
                    args.approval_ledger_anchor_path
                ),
                anchor_key_path=args.anchor_key_path,
            ),
        )

        apply_journal = ApplyOutcomeJournal(
            path=args.apply_journal
        )

        _report_startup_reconciliation(
            apply_journal,
            args.allowed_path,
            approval_store,
        )

        agent = build_recovery_agent(
            kernel,
            worker_executor=WorkerExecutor(
                allowed_paths=tuple(args.allowed_path),
            ),
            risk_engine=risk_engine,
            risk_policy=RiskPolicy(),
            approval_store=approval_store,
            evidence_recorder=recorder,
            apply_journal=apply_journal,
        )

        print(
            "\n[recovery mode] apply+verify+bounded recovery "
            "active, risk-classified, approval store-backed "
            "(no interactive approval: HIGH/CRITICAL/UNKNOWN "
            "require a pre-granted ledger approval and fail "
            "closed otherwise)."
        )

        if args.approval_ledger_anchor_path is None:

            print(
                "\n[approval ledger] UNANCHORED: no "
                "--approval-ledger-anchor-path given. The ledger's "
                "unkeyed chain can be truncated/forged by a data-dir "
                "writer (a consumed approval could be resurrected). "
                "For a security-sensitive deployment pass "
                "--approval-ledger-anchor-path (key via "
                "CHAIN_ANCHOR_KEY or --anchor-key-path)."
            )

        else:

            print(
                "[approval ledger] ANCHORED: ledger tail integrity is "
                "verified against the keyed chain-head trust anchor "
                "on every reload."
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


def _report_startup_reconciliation(
    apply_journal,
    allowed_path,
    approval_store,
):

    """Detect-only restart reconciliation for the apply journal.

    Prints a summary of any orphaned apply intents. Never mutates a
    file and never bypasses the approval boundary; a corrupt journal
    raises ``RuntimeError`` (fail-closed startup).
    """

    print("\n[startup reconciliation] scanning apply journal...")

    report = run_startup_reconciliation(
        apply_journal,
        allowed_paths=tuple(allowed_path),
        approval_store=approval_store,
    )

    if not report.intents:

        print("[startup reconciliation] no apply intents found.")

        return

    print(
        f"[startup reconciliation] {len(report.intents)} "
        "apply intent(s) found."
    )

    for status in report.intents:

        print(
            f"  - {status.intent_id} {status.classification} "
            f"mutation_present={status.mutation_present}"
        )

    if report.orphaned_mutations:

        print(
            "[startup reconciliation] ORPHANED MUTATIONS "
            "DETECTED (see report; detection only, no repair)."
        )

    for anomaly in report.anomalies:

        print(f"[startup reconciliation] anomaly: {anomaly}")


if __name__ == "__main__":

    main()