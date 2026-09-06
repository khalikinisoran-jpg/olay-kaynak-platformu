"""Shared evidence helpers for the Tanuq product shell.

Read-only inspection of the existing durable stores (EventStore,
ChainAnchor, ApprovalLedger, ApplyOutcomeJournal). Nothing here
creates, mutates or authorizes anything.
"""
import json

from simulation.persistence.chain_anchor import ChainAnchor
from simulation.security.hash_verifier import HashVerifier

from tanuq import __version__
from tanuq.config import now_iso, tanuq_data_dir

GENESIS_HASH = "GENESIS"


def read_event_records(data_dir, events_file_name="events.jsonl"):
    path = data_dir / events_file_name
    records = []
    if not path.exists():
        return records
    with open(path, "r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                records.append(json.loads(line))
    return records


def chain_status(data_dir, anchor_key):
    records = read_event_records(data_dir)
    chain_valid = HashVerifier().verify(records)
    tail_sequence = records[-1]["sequence"] if records else 0
    tail_hash = records[-1]["current_hash"] if records else GENESIS_HASH
    anchor_state = "MISSING"
    if anchor_key is not None:
        try:
            anchor = ChainAnchor(
                path=str(data_dir / "chain_anchor.jsonl"),
                anchor_key=anchor_key,
            )
            anchor_state = (
                "ACTIVE"
                if anchor.verify(tail_sequence, tail_hash)
                else "FAILED"
            )
        except Exception:
            anchor_state = "UNAVAILABLE"
    return {
        "events": len(records),
        "chain_valid": chain_valid,
        "anchor": anchor_state,
    }


def journal_intents(apply_journal, limit=None):
    records = apply_journal.load()
    if not records:
        return []
    order, grouped = apply_journal.intents(records)
    if limit and limit > 0:
        order = order[-limit:]
    intents = []
    for intent_id in order:
        rows = grouped[intent_id]
        first = rows[0]
        last = rows[-1].get("record_type", "")
        terminal = last.upper() if last else "UNKNOWN"
        intents.append({
            "intent_id": intent_id,
            "path": first.get("path", ""),
            "fingerprint": first.get("patch_fingerprint", ""),
            "risk": first.get("risk_level", ""),
            "approval_id": first.get("approval_id", ""),
            "lifecycle": [r.get("record_type", "") for r in rows],
            "terminal": terminal,
        })
    return intents


def blocked_from_events(data_dir, limit=None):
    """Blocked actions derived ONLY from recorded evidence events.

    Sources: WorkerPatchValidated with valid=False and
    WorkerRiskAssessed with allowed=False. No UI-owned state.
    """
    records = read_event_records(data_dir)
    by_fingerprint = {}
    for record in records:
        etype = record.get("event_type", "")
        payload = record.get("payload", {}) or {}
        fingerprint = payload.get("patch_fingerprint", "")
        if etype == "WorkerPatchValidated" and payload.get("valid") is False:
            entry = by_fingerprint.setdefault(fingerprint, {
                "fingerprint": fingerprint,
                "path": payload.get("path", ""),
                "reason": payload.get("message", ""),
                "risk": "",
                "sequence": record.get("sequence"),
            })
            entry["reason"] = payload.get("message", "")
        elif etype == "WorkerRiskAssessed" and payload.get("allowed") is False:
            entry = by_fingerprint.setdefault(fingerprint, {
                "fingerprint": fingerprint,
                "path": payload.get("path", ""),
                "reason": payload.get("reason", ""),
                "risk": "",
                "sequence": record.get("sequence"),
            })
            entry["risk"] = payload.get("risk_level", "")
            if payload.get("reason"):
                entry["reason"] = payload.get("reason", "")
    blocked = [
        v for v in by_fingerprint.values()
        if v["fingerprint"]
    ]
    blocked.sort(key=lambda item: item.get("sequence") or 0)
    if limit and limit > 0:
        blocked = blocked[-limit:]
    return blocked


def event_summary(records, limit=200):
    rows = []
    for record in records[-limit:]:
        payload = record.get("payload", {}) or {}
        rows.append({
            "sequence": record.get("sequence"),
            "event_type": record.get("event_type", ""),
            "event_id": record.get("event_id", ""),
            "path": payload.get("path", ""),
            "fingerprint": payload.get("patch_fingerprint", ""),
            "result": (
                payload.get("valid")
                if "valid" in payload
                else payload.get("terminal", payload.get("status", ""))
            ),
            "timestamp": payload.get("created_at", payload.get("granted_at", "")),
            "current_hash": record.get("current_hash", ""),
            "previous_hash": record.get("previous_hash", ""),
        })
    return rows


def export_evidence(env) -> dict:
    """Read-only, secret-safe audit bundle for hand-off/archival.

    Pure projection over the durable stores: identity/config summary,
    chain + anchor status, per-operation lineage and active incidents.
    Contains no patch content, no secret material, no token values.
    """
    from tanuq.incidents import collect_incidents

    chain = chain_status(tanuq_data_dir(env.workspace), env.store.chain_anchor.key)
    report = lineage(env)
    ops = operations(env)
    incidents = collect_incidents(env)
    return {
        "product": "TANUQ",
        "version": __version__,
        "generated_at": now_iso(),
        "workspace": str(env.workspace),
        "protected_scope": list(env.config.allowed_paths),
        "governed": True,
        "verification_depth": env.config.verification_depth,
        "evidence": {
            "chain_valid": chain["chain_valid"],
            "anchor": chain["anchor"],
            "events": chain["events"],
        },
        "lineage": report,
        "operations": ops,
        "incidents": {
            "total": incidents["total"],
            "critical": incidents["critical"],
            "items": incidents["incidents"],
        },
        "note": (
            "Evidence is tamper-evident (detectable), not tamper-proof. "
            "This bundle contains fingerprint/hash references only."
        ),
    }


def terminal_state(pipeline_result):
    """User-facing terminal state derived from the pipeline result.

    The journal remains the authoritative evidence; this only maps the
    pipeline outcome (including its failure stage) to a product label.
    """
    if pipeline_result is None:
        return "NOT_RUN", ""
    stage = pipeline_result.failure_stage or ""
    if pipeline_result.success:
        return "VERIFIED", stage
    if stage == "verification" and pipeline_result.patch_results:
        pr = pipeline_result.patch_results[0].pipeline_result
        if pr is not None and getattr(pr, "rollback", None) is not None:
            rb = pr.rollback
            return ("ROLLED_BACK" if rb.success else "ROLLBACK_FAILED"), stage
        return "FAILED", stage
    if stage == "rollback":
        return "ROLLBACK_FAILED", stage
    mapping = {
        "validation": "DENIED",
        "risk": "DENIED",
        "approval": "DENIED",
        "controller": "DENIED",
        "apply": "FAILED",
        "worker": "FAILED",
        "unexpected": "FAILED",
    }
    return mapping.get(stage, stage.upper() or "FAILED"), stage


def lineage(env, fingerprint=None, limit=20):
    """Cross-journal operation lineage keyed by proposal fingerprint.

    Stitches the durable evidence sources into one chain per
    operation: proposal -> risk decision -> approvals -> execution ->
    verification/rollback. Fingerprint/hash references only; never
    patch content or secret material. Read-only projection.
    """
    data_dir = tanuq_data_dir(env.workspace)
    chains = {}

    def chain(fp):
        return chains.setdefault(fp, {
            "fingerprint": fp,
            "fingerprint_short": fp[:12] if fp else "",
            "path": "",
            "proposal": None,
            "risk": None,
            "approvals": {},
            "execution": None,
            "outcome": None,
            "denied_reason": None,
            "sessions": [],
            "refs": [],
        })

    for record in read_event_records(data_dir):
        event_type = record.get("event_type", "")
        payload = record.get("payload", {}) or {}
        fp = payload.get("patch_fingerprint", "")
        seq = record.get("sequence")
        if not fp:
            continue
        c = chain(fp)
        c["refs"].append(seq)
        task_id = str(payload.get("task_id", ""))
        if task_id.startswith("tanuq-session:"):
            session = task_id.split(":", 1)[1]
            if session not in c["sessions"]:
                c["sessions"].append(session)
        if event_type == "WorkerPatchProposed":
            c["proposal"] = {
                "path": payload.get("path", ""),
                "action": payload.get("action", ""),
                "reason": payload.get("reason", ""),
                "task_id": task_id,
                "seq": seq,
            }
        elif event_type == "WorkerRiskAssessed":
            c["risk"] = {
                "risk": payload.get("risk_level", ""),
                "reason": payload.get("reason", ""),
                "allowed": payload.get("allowed"),
                "approval_required": payload.get("requires_human_approval"),
                "signals": [list(s) for s in payload.get("signals", ()) or ()],
                "seq": seq,
            }
        elif event_type == "WorkerPatchValidated" and payload.get("valid") is False:
            c["outcome"] = "DENIED"
            c["denied_reason"] = payload.get("message", "")
        elif event_type == "WorkerHumanApprovalGranted":
            approval = c["approvals"].setdefault(payload.get("approval_id", ""), {})
            approval.update({
                "approval_id": payload.get("approval_id", ""),
                "authorizer": payload.get("authorizer", ""),
                "risk": payload.get("risk_level", ""),
                "created_at": payload.get("created_at", ""),
                "expires_at": payload.get("expires_at", ""),
            })
        elif event_type == "WorkerVerificationCompleted":
            c["outcome"] = "VERIFIED"
        elif event_type == "WorkerVerificationFailed":
            c["outcome"] = "VERIFICATION_FAILED"
        elif event_type == "WorkerRollbackSucceeded":
            c["outcome"] = "ROLLED_BACK"
        elif event_type == "WorkerRollbackFailed":
            c["outcome"] = "ROLLBACK_FAILED"

    for intent in journal_intents(env.apply_journal):
        c = chain(intent["fingerprint"])
        c["execution"] = {
            "intent_id": intent["intent_id"],
            "lifecycle": intent["lifecycle"],
            "terminal": intent["terminal"],
            "approval_id": intent.get("approval_id", ""),
        }
        c["outcome"] = intent["terminal"]
        if intent.get("path") and not c["path"]:
            c["path"] = intent["path"]

    try:
        ledger_records = env.approval_store.ledger.load()
    except Exception:
        ledger_records = []
    for record in ledger_records:
        fp = record.get("patch_fingerprint", "")
        record_type = record.get("record_type", "")
        if not fp or record_type in ("anchored",):
            continue
        approval = chain(fp)["approvals"].setdefault(
            record.get("approval_id", ""), {}
        )
        approval["approval_id"] = record.get("approval_id", "")
        approval["status"] = record_type
        if record.get("authorizer"):
            approval["authorizer"] = record.get("authorizer")
        if record.get("created_at"):
            approval["created_at"] = record.get("created_at")

    results = []
    for fp, c in chains.items():
        if fingerprint and not fp.startswith(fingerprint):
            continue
        c["approvals"] = list(c["approvals"].values())
        if c["proposal"] and not c["path"]:
            c["path"] = c["proposal"]["path"]
        c["refs"] = [r for r in c["refs"] if r is not None]
        c["last_seq"] = max(c["refs"]) if c["refs"] else 0
        results.append(c)
    results.sort(key=lambda c: c["last_seq"], reverse=True)
    if limit and limit > 0:
        results = results[:limit]
    return {"chains": results, "count": len(results)}


def operations(env, fingerprint=None, operation_id=None, limit=20):
    """Product-level Operation view: one projection per governance
    lifecycle, computed from lineage chains (single computation path
    shared with lineage/history/UI). States are readable projections
    of authoritative journal/event/approval states - never invented:

        journal terminal verified        -> VERIFIED
        journal terminal rolled_back     -> ROLLED_BACK
        journal terminal rollback_failed -> INCIDENT
        journal terminal apply_failed    -> FAILED
        journal non-terminal (crash)     -> INCIDENT
        granted approval, no execution   -> APPROVED
        risk requires approval           -> PENDING_APPROVAL
        policy/scope denial              -> DENIED
        otherwise                        -> PROPOSED
    """
    from tanuq.incidents import collect_incidents
    from tanuq.pending import load_pending

    chains = lineage(env, fingerprint=fingerprint, limit=None)["chains"]
    pending_fps = {
        r.get("fingerprint") for r in load_pending(env.workspace)
    }
    incident_report = collect_incidents(env)
    incidents_by_operation = {}
    incidents_by_fingerprint = {}
    for incident in incident_report["incidents"]:
        if incident.get("operation"):
            incidents_by_operation.setdefault(
                incident["operation"], []
            ).append(incident["type"])
        if incident.get("fingerprint"):
            incidents_by_fingerprint.setdefault(
                incident["fingerprint"], []
            ).append(incident["type"])

    op_filter = operation_id
    operations = []
    for c in chains:
        execution = c.get("execution")
        approvals = c.get("approvals", [])
        granted_open = any(
            a.get("status", "grant") == "grant" for a in approvals
        )
        if execution:
            terminal = str(execution["terminal"]).lower()
            state = {
                "verified": "VERIFIED",
                "rolled_back": "ROLLED_BACK",
                "rollback_failed": "INCIDENT",
                "apply_failed": "FAILED",
            }.get(terminal, "INCIDENT")
            resolved_id = execution["intent_id"]
        elif c.get("outcome") == "DENIED":
            state = "DENIED"
            resolved_id = "fp-" + c["fingerprint_short"]
        elif granted_open:
            state = "APPROVED"
            resolved_id = "fp-" + c["fingerprint_short"]
        elif c.get("risk") and c["risk"].get("approval_required"):
            state = "PENDING_APPROVAL"
            resolved_id = "fp-" + c["fingerprint_short"]
        elif c.get("risk") and c["risk"].get("allowed") is False:
            state = "DENIED"
            resolved_id = "fp-" + c["fingerprint_short"]
        else:
            state = "PROPOSED"
            resolved_id = "fp-" + c["fingerprint_short"]

        linked_incidents = sorted(set(
            incidents_by_operation.get(execution["intent_id"], [])
            if execution else []
        ) | set(
            incidents_by_fingerprint.get(c["fingerprint"], [])
        ))
        operations.append({
            "operation_id": resolved_id,
            "fingerprint": c["fingerprint"],
            "fingerprint_short": c["fingerprint_short"],
            "path": c.get("path", ""),
            "sessions": c.get("sessions", []),
            "proposal": c.get("proposal"),
            "risk": c.get("risk"),
            "approvals": approvals,
            "execution": execution,
            "denied_reason": c.get("denied_reason"),
            "outcome": c.get("outcome"),
            "state": state,
            "incidents": linked_incidents,
            "in_pending": c["fingerprint"] in pending_fps,
            "evidence_refs": {
                "first_seq": min(c["refs"]) if c["refs"] else None,
                "last_seq": max(c["refs"]) if c["refs"] else None,
                "events": len(c["refs"]),
            },
        })
    if operation_id:
        operations = [
            o for o in operations
            if o["operation_id"].startswith(op_filter)
        ]
    operations.sort(key=lambda o: o["evidence_refs"]["last_seq"] or 0,
                    reverse=True)
    if limit and limit > 0:
        operations = operations[:limit]
    return {"operations": operations, "count": len(operations)}
