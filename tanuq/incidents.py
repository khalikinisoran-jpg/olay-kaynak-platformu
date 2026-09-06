"""Tanuq Incident Center — product projection over durable evidence.

Aggregates every observable failure state into user-visible incidents.
Detection ONLY: nothing here repairs, rolls back, re-authors or
bypasses the approval boundary (core contract, MISSION-019). Recovery
remains an explicit, separately-authorized operator decision.

Sources (no parallel audit state):
- ApplyOutcomeJournal via the existing detect-only startup
  reconciliation (orphaned apply intents, pending intents,
  rollback failures, consumed approvals without outcome);
- EventStore + ChainAnchor status (evidence chain validity, anchor);
- pending/journal corruption surfaced as fail-closed incidents.
"""
from datetime import datetime, timezone

from simulation.agent.recovery.recovery_assembly import (
    run_startup_reconciliation,
)
from simulation.agent.recovery.startup_reconciliation import (
    CLASS_INTENT_ONLY,
    CLASS_ORPHANED_APPLIED,
    CLASS_ORPHANED_APPLY_START,
    CLASS_ORPHANED_ROLLBACK,
    CLASS_ROLLBACK_FAILED,
)

ORPHAN_CLASSES = {
    CLASS_ORPHANED_APPLIED: "orphaned_apply",
    CLASS_ORPHANED_APPLY_START: "crashed_during_apply",
    CLASS_ORPHANED_ROLLBACK: "crashed_during_rollback",
}

RECOMMENDATIONS = {
    "orphaned_apply": (
        "Inspect the target file. If the change is unwanted, restore it "
        "manually or via a new governed proposal; the evidence journal "
        "records the crash point."
    ),
    "crashed_during_apply": (
        "The process crashed while applying. Verify the target file "
        "state manually; atomic write means it is either old or new "
        "content, never truncated."
    ),
    "crashed_during_rollback": (
        "A rollback was interrupted. Compare the file against the "
        "journaled content hashes before any further action."
    ),
    "pending_intent": (
        "An apply intent was opened but never started. Usually harmless; "
        "it stays as evidence of a proposed-but-never-executed change."
    ),
    "rollback_failed": (
        "Automatic rollback FAILED. The workspace may hold an "
        "unverified change. Inspect the target file and restore it "
        "manually if required."
    ),
    "consumed_approval_no_outcome": (
        "An approval was consumed but its operation never reached a "
        "terminal outcome. Treat the related approval as spent "
        "(single-use); a fresh approval is required for any retry."
    ),
    "reconciliation_anomaly": (
        "The journal contains an anomalous transition. Inspect "
        ".tanuq/data/apply_journal.jsonl and do not trust the affected "
        "operation's history."
    ),
    "evidence_chain_invalid": (
        "The event chain is INVALID. Do not trust the recorded history; "
        "investigate before continuing to use this workspace."
    ),
    "anchor_failed": (
        "The keyed chain-head anchor does not match the event tail. "
        "Evidence may have been modified or the anchor key changed."
    ),
    "anchor_missing": (
        "No anchor records exist yet; the anchor activates with the "
        "first recorded event. If events exist while the anchor file is "
        "missing, treat evidence as unverified."
    ),
    "journal_corrupt": (
        "The apply journal failed verification (hash/state). Fail-closed: "
        "operations that depend on it are refused."
    ),
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def collect_incidents(env) -> dict:
    """Detect-only incident report for a loaded workspace environment."""
    incidents = []

    journal_ok = True
    try:
        env.apply_journal.load()
    except Exception as exc:
        journal_ok = False
        incidents.append(_incident(
            "journal_corrupt", "critical",
            operation="", path=str(env.apply_journal.path),
            current_state="corrupt / failed verification",
            recovery_status="fail-closed; no repair attempted",
            detail=str(exc),
        ))

    if journal_ok:
        try:
            report = run_startup_reconciliation(
                env.apply_journal,
                allowed_paths=tuple(env.config.allowed_paths),
                approval_store=env.approval_store,
            )
        except Exception as exc:
            incidents.append(_incident(
                "journal_corrupt", "critical",
                operation="", path="apply_journal",
                current_state="reconciliation failed",
                recovery_status="fail-closed; no repair attempted",
                detail=str(exc),
            ))
        else:
            for status in report.intents:
                incident = _intent_incident(status)
                if incident:
                    incidents.append(incident)
            for approval_id in report.consumed_approvals_without_outcome:
                incidents.append(_incident(
                    "consumed_approval_no_outcome", "warning",
                    operation=approval_id, path="",
                    current_state="consumed, no terminal outcome",
                    recovery_status="approval spent (single-use)",
                ))
            for anomaly in report.anomalies:
                incidents.append(_incident(
                    "reconciliation_anomaly", "warning",
                    operation="", path="",
                    current_state="anomalous journal transition",
                    recovery_status="detect-only",
                    detail=str(anomaly),
                ))

    from tanuq.config import read_anchor_key, tanuq_data_dir
    from tanuq.evidence import chain_status

    try:
        key = read_anchor_key(env.workspace)
    except Exception:
        key = None
    chain = chain_status(tanuq_data_dir(env.workspace), key)
    if not chain["chain_valid"] and chain["events"]:
        incidents.append(_incident(
            "evidence_chain_invalid", "critical",
            operation="", path="events.jsonl",
            current_state=f"{chain['events']} events, chain INVALID",
            recovery_status="fail-closed",
        ))
    if chain["anchor"] == "FAILED":
        incidents.append(_incident(
            "anchor_failed", "critical",
            operation="", path="chain_anchor.jsonl",
            current_state="anchor does not match chain head",
            recovery_status="fail-closed",
        ))
    elif chain["anchor"] == "UNAVAILABLE":
        incidents.append(_incident(
            "anchor_missing", "warning",
            operation="", path="chain_anchor.jsonl",
            current_state="anchor could not be opened (key missing?)",
            recovery_status="fail-closed",
        ))

    incidents.sort(key=lambda i: (0 if i["severity"] == "critical" else 1, i["type"]))
    counts = {}
    for incident in incidents:
        counts[incident["type"]] = counts.get(incident["type"], 0) + 1
    return {
        "incidents": incidents,
        "counts": counts,
        "total": len(incidents),
        "critical": sum(1 for i in incidents if i["severity"] == "critical"),
        "detected_at": _now(),
    }


def _intent_incident(status):
    state = {
        CLASS_ORPHANED_APPLIED: "applied, outcome never journaled (crash)",
        CLASS_ORPHANED_APPLY_START: "apply started, process crashed",
        CLASS_ORPHANED_ROLLBACK: "rollback started, process crashed",
        CLASS_INTENT_ONLY: "intent opened, apply never started",
        CLASS_ROLLBACK_FAILED: "automatic rollback FAILED",
    }.get(status.classification)
    if state is None:
        return None
    if status.classification == CLASS_INTENT_ONLY:
        itype, severity = "pending_intent", "warning"
    elif status.classification == CLASS_ROLLBACK_FAILED:
        itype, severity = "rollback_failed", "critical"
    else:
        itype, severity = ORPHAN_CLASSES[status.classification], "critical"
    mutation = (
        f" mutation_present={status.mutation_present}"
        if status.mutation_present is not None
        else ""
    )
    return _incident(
        itype, severity,
        operation=status.intent_id,
        path=status.path,
        current_state=state + mutation,
        recovery_status="detect-only; operator decision required",
        detail=f"fingerprint={status.patch_fingerprint[:12]} attempt={status.attempt}",
        fingerprint=status.patch_fingerprint,
    )


def _incident(itype, severity, operation, path, current_state,
              recovery_status, detail="", fingerprint=""):
    return {
        "type": itype,
        "severity": severity,
        "detected": _now(),
        "operation": operation,
        "fingerprint": fingerprint,
        "path": path,
        "current_state": current_state,
        "recovery_status": recovery_status,
        "recommended_action": RECOMMENDATIONS.get(
            itype, "Investigate before continuing."
        ),
        "detail": detail,
    }
