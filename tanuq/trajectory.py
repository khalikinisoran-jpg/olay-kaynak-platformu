"""Read-only trajectory telemetry projection.

Derives per-path trajectory state from the EXISTING evidence events
(the same records the action governance pipeline already wrote).
Observation only — this module never enforces anything:

- it does not request approvals or change approval state
- it does not make or alter risk/policy decisions
- it does not authorize or execute anything
- it does not write, mutate or rewrite any evidence file
- it introduces no new identity semantics (no agent identity, no
  path-family model, no task semantics)

Fields that the evidence does not carry are reported as absent values
(0 / empty) — never invented: no wall-clock density (no event-level
timestamps), no cumulative diff (no patch content in evidence), no
semantic behavior (fingerprints are opaque hashes).

Read path: ``tanuq.evidence.read_event_records`` — the same canonical
read interface used by ``lineage``/``chain_status``.
"""
from collections import OrderedDict

from tanuq.config import tanuq_data_dir
from tanuq.evidence import read_event_records

_SUCCESS_OUTCOMES = ("VERIFIED", "APPLIED")

_VERIFICATION_EVENTS = {
    "WorkerVerificationCompleted": True,
    "WorkerVerificationFailed": False,
}


def _op_outcome(types):
    """Outcome for one fingerprint's event-type list (deterministic)."""
    if "WorkerVerificationCompleted" in types:
        return "VERIFIED"
    if "WorkerRollbackSucceeded" in types:
        return "ROLLED_BACK"
    if "WorkerRollbackFailed" in types:
        return "ROLLBACK_FAILED"
    if "WorkerVerificationFailed" in types:
        return "VERIFICATION_FAILED"
    if "WorkerPatchApplyFailed" in types:
        return "APPLY_FAILED"
    if "WorkerPatchApplied" in types:
        return "APPLIED"
    return "PROPOSED"


def _collect(records):
    """Group evidence records into per-fingerprint operations."""
    chains = OrderedDict()
    for record in records:
        payload = record.get("payload", {}) or {}
        fingerprint = payload.get("patch_fingerprint", "")
        if not fingerprint:
            continue
        chain = chains.setdefault(fingerprint, [])
        chain.append({
            "sequence": record.get("sequence", 0),
            "event_type": record.get("event_type", ""),
            "payload": payload,
        })
    return chains


def _operation(fingerprint, chain):
    types = [event["event_type"] for event in chain]
    sequence = min(event["sequence"] for event in chain)
    proposal = next((e["payload"] for e in chain
                     if e["event_type"] == "WorkerPatchProposed"), None)
    risk = next((e["payload"] for e in chain
                 if e["event_type"] == "WorkerRiskAssessed"), None)
    denied = any(
        e["event_type"] == "WorkerPatchValidated"
        and e["payload"].get("valid") is False
        for e in chain
    ) or (risk is not None and risk.get("allowed") is False)
    if proposal is not None:
        path = proposal.get("path", "")
        action = proposal.get("action", "")
        task_id = proposal.get("task_id", "")
    elif risk is not None:
        path = risk.get("path", "")
        action = risk.get("action", "")
        task_id = risk.get("task_id", "")
    else:
        path = ""
        action = ""
        task_id = ""
    verified_values = [
        _VERIFICATION_EVENTS[e["event_type"]] for e in chain
        if e["event_type"] in _VERIFICATION_EVENTS
    ]
    approval_granted = "WorkerHumanApprovalGranted" in types
    applied = "WorkerPatchApplied" in types
    approval_required = bool(
        risk.get("requires_human_approval", False) if risk else False)
    outcome = "DENIED" if denied else _op_outcome(types)
    succeeded = applied and outcome in _SUCCESS_OUTCOMES
    return {
        "fingerprint": fingerprint,
        "path": path,
        "action": action,
        "sequence": sequence,
        "risk": (risk or {}).get("risk_level", ""),
        "risk_signals": [
            [str(name), str(value)]
            for name, value in (risk or {}).get("signals", ()) or ()
        ],
        "outcome": outcome,
        "verified": (verified_values[-1] if verified_values else None),
        "approval_required": approval_required,
        "approval_granted": approval_granted,
        "auto_apply": bool(succeeded and not approval_required),
        "sessions": [task_id.split(":", 1)[1]]
        if task_id.startswith("tanuq-session:") else [],
        "_task_id": task_id,
        "_succeeded_auto": bool(succeeded and not approval_required
                                and action == "modify"),
    }


def _trajectory_fields(ops):
    """Trajectory-level aggregation over one path's ordered operations."""
    risk_sequence = [op["risk"] for op in ops]
    outcome_sequence = [op["outcome"] for op in ops]
    verification_sequence = [op["verified"] for op in ops]
    risk_transitions = [
        [risk_sequence[i], risk_sequence[i + 1]]
        for i in range(len(risk_sequence) - 1)
        if risk_sequence[i] != risk_sequence[i + 1]
    ]
    longest_auto_run = 0
    run = 0
    for op in ops:
        if op["_succeeded_auto"]:
            run += 1
            longest_auto_run = max(longest_auto_run, run)
        else:
            run = 0
    return {
        "operation_count": len(ops),
        "consecutive_auto_apply_count": longest_auto_run,
        "risk_sequence": risk_sequence,
        "outcome_sequence": outcome_sequence,
        "verification_sequence": verification_sequence,
        "risk_transitions": risk_transitions,
        "failure_count": sum(
            1 for o in ops
            if o["outcome"] in ("VERIFICATION_FAILED", "APPLY_FAILED")
        ),
        "rollback_count": sum(
            1 for o in ops
            if o["outcome"] in ("ROLLED_BACK", "ROLLBACK_FAILED")
        ),
    }


def trajectory_projection(env, path=None):
    """Read-only trajectory telemetry over the workspace's evidence.

    Returns a deterministic dict grouped by exact recorded path. This
    is an observation projection: calling it has no effect on any
    store, decision or authorization state.
    """
    records = read_event_records(tanuq_data_dir(env.workspace))
    chains = _collect(records)
    operations = [
        _operation(fingerprint, chain)
        for fingerprint, chain in chains.items()
    ]
    operations.sort(key=lambda op: op["sequence"])
    by_path = OrderedDict()
    for op in operations:
        if path is not None and op["path"] != path:
            continue
        by_path.setdefault(op["path"], []).append(op)
    projections = []
    for op_path in sorted(by_path):
        ops = by_path[op_path]
        entry = _trajectory_fields(ops)
        entry["path"] = op_path
        entry["operations"] = [
            {
                "fingerprint": op["fingerprint"],
                "action": op["action"],
                "sequence": op["sequence"],
                "risk": op["risk"],
                "risk_signals": op["risk_signals"],
                "outcome": op["outcome"],
                "verified": op["verified"],
                "approval_required": op["approval_required"],
                "approval_granted": op["approval_granted"],
                "auto_apply": op["auto_apply"],
                "sessions": op["sessions"],
            }
            for op in ops
        ]
        projections.append(entry)
    return {
        "workspace": str(env.workspace),
        "operation_count": len(operations) if path is None else sum(
            len(e["operations"]) for e in projections),
        "path_count": len(projections),
        "paths": projections,
    }
