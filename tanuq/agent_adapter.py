"""Tanuq agent-adapter — a thin, agent-agnostic hook protocol.

Any external coding agent can drive Tanuq through this layer without
knowing anything about the Python internals:

    propose  : submit JSON proposal(s), get a machine-readable verdict
    approve  : grant a single-use, fingerprint-bound approval
    execute  : run pending proposal(s) through the governed pipeline

The adapter invents NO authorization or security mechanism. It only
connects existing primitives:

    PathPolicy (scope) -> GovernanceEvaluator (deterministic risk)
    -> ApprovalStore (single-use, fingerprint-bound)
    -> WorkerActionPipeline (validate->risk->approval->controller
       ->apply->verify->rollback)
    -> ApplyOutcomeJournal / EventStore / ChainAnchor evidence
    -> WorkerEvidenceRecorder (denial evidence for blocked actions)
"""
import json

from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.agent.worker.worker_result import WorkerResult
from simulation.security.path_policy import PathPolicy

from tanuq.config import APPROVAL_TTL_SECONDS
from tanuq.evidence import terminal_state
from tanuq.pending import load_pending, patch_from_record, remove_pending, save_pending
from tanuq.verification_profile import select_test_targets

REQUIRED_FIELDS = ("path", "old_content", "new_content")
ALLOWED_ACTIONS = ("modify",)


class ProtocolError(Exception):
    """Malformed hook input (JSON, shape or required fields)."""


def parse_payload(raw_text):
    """Parse hook stdin. Accepts one proposal object or an array."""
    try:
        data = json.loads(raw_text)
    except Exception as exc:
        raise ProtocolError(f"proposal JSON could not be parsed: {exc}")
    items = data if isinstance(data, list) else [data]
    if not items or not all(isinstance(i, dict) for i in items):
        raise ProtocolError("proposal payload must be a JSON object or an array of objects")
    return items


def _validate_item(obj):
    for field in REQUIRED_FIELDS:
        if field not in obj or obj[field] is None:
            raise ProtocolError(f"missing required field: {field}")
    action = obj.get("action", "modify")
    if action not in ALLOWED_ACTIONS:
        raise ProtocolError(
            f"unsupported action {action!r}: this product governs "
            f"file modifications only ({list(ALLOWED_ACTIONS)})"
        )
    return {
        "path": str(obj["path"]),
        "action": action,
        "reason": str(obj.get("reason", "agent proposal")),
        "old_content": obj["old_content"],
        "new_content": obj["new_content"],
    }


def _propose_one(env, obj):
    item = _validate_item(obj)
    patch = PatchProposal(
        path=item["path"],
        action=item["action"],
        reason=item["reason"],
        old_content=item["old_content"],
        new_content=item["new_content"],
        allowed_paths=tuple(env.config.allowed_paths),
    )
    fingerprint = patch.fingerprint()
    base = {
        "path": patch.path,
        "action": patch.action,
        "reason": patch.reason,
        "fingerprint": fingerprint,
        "fingerprint_short": fingerprint[:12],
        "diff": {
            "old_preview": patch.old_content[:2000],
            "new_preview": patch.new_content[:2000],
            "old_len": len(patch.old_content),
            "new_len": len(patch.new_content),
        },
    }
    in_scope, scope_message = PathPolicy().check_scope(
        patch.path, tuple(env.config.allowed_paths)
    )
    if not in_scope:
        denial = f"outside the protected workspace ({scope_message})"
        env.recorder.record_patch_proposed("tanuq-agent", patch)
        env.recorder.record_patch_validated(
            "tanuq-agent", patch, False, f"DENIED: {denial}"
        )
        base.update({
            "state": "DENIED",
            "risk": "UNKNOWN",
            "approval_required": False,
            "denial_reason": denial,
            "message": f"DENIED: {denial}",
            "governance": None,
        })
        return base
    decision = env.governance.evaluate(patch)
    env.recorder.record_patch_proposed("tanuq-agent", patch)
    env.recorder.record_risk_assessed("tanuq-agent", patch, decision)
    if decision.allowed is not True:
        base.update({
            "state": "DENIED",
            "risk": decision.risk_level.value,
            "approval_required": False,
            "denial_reason": f"denied by deterministic policy ({decision.risk_level.value})",
            "message": f"DENIED by policy (risk {decision.risk_level.value}).",
            "governance": _governance_view(decision),
        })
        return base
    approval_required = decision.requires_human_approval is True
    base.update({
        "state": "APPROVAL_REQUIRED" if approval_required else "PROPOSED",
        "risk": decision.risk_level.value,
        "approval_required": approval_required,
        "denial_reason": None,
        "message": (
            f"Risk: {decision.risk_level.value} — approval required "
            f"(single-use, fingerprint-bound, TTL {APPROVAL_TTL_SECONDS}s)."
            if approval_required
            else f"Risk: {decision.risk_level.value} — accepted; it will "
                 "apply on execute with verification and rollback."
        ),
        "governance": _governance_view(decision),
        "what_this_authorizes": (
            f"Approving authorizes EXACTLY this change: {patch.action} "
            f"on {patch.path} replacing the approved old content with the "
            f"approved new content. The approval is bound to fingerprint "
            f"{fingerprint[:12]} and is single-use (expires "
            f"{APPROVAL_TTL_SECONDS}s after granting). Any other change "
            "requires a new approval."
        ) if approval_required else None,
    })
    return base


def _governance_view(decision):
    signals = [
        [str(name), str(value)]
        for name, value in getattr(decision.assessment, "signals", ()) or ()
    ]
    return {
        "risk": decision.risk_level.value,
        "allowed": bool(decision.allowed),
        "approval_required": bool(decision.requires_human_approval),
        "reason": decision.reason,
        "assessment_reason": getattr(decision.assessment, "reason", ""),
        "signals": signals,
    }


def propose(env, payload_text, session=None):
    """Hook entry: raw stdin text -> machine-readable verdict."""
    items = parse_payload(payload_text)
    results = []
    accepted = []
    for obj in items:
        result = _propose_one(env, obj)
        if session:
            result["session"] = session
        results.append(result)
        patch_ok = result.get("state") in ("PROPOSED", "APPROVAL_REQUIRED")
        if patch_ok:
            accepted.append(PatchProposal(
                path=result["path"],
                action=result["action"],
                reason=result["reason"],
                old_content=obj["old_content"],
                new_content=obj["new_content"],
                allowed_paths=tuple(env.config.allowed_paths),
            ))
    if accepted:
        save_pending(env.workspace, accepted, session=session)
    verdicts = [r for r in results if r.get("state") != "ERROR"]
    return {
        "proposals": results,
        "denied": any(r.get("state") == "DENIED" for r in verdicts) or not accepted,
        "pending_count": len(load_pending(env.workspace)),
        "session": session,
    }


def approve(env, fingerprint=None):
    """Grant single-use approvals for pending HIGH/CRITICAL proposals."""
    pending = load_pending(env.workspace)
    if fingerprint:
        pending = [
            r for r in pending
            if r.get("fingerprint", "").startswith(fingerprint)
        ]
    granted = []
    for record in pending:
        try:
            patch = patch_from_record(record)
        except Exception:
            continue
        decision = env.governance.evaluate(patch)
        if decision.requires_human_approval is not True:
            continue
        fp = patch.fingerprint()
        if record.get("fingerprint") and record["fingerprint"] != fp:
            continue
        approval = env.approval_store.grant(
            patch_fingerprint=fp,
            path=patch.path,
            action=patch.action,
            risk_level=decision.risk_level.value,
            attempt=1,
            authorizer="human-operator",
        )
        granted.append({
            "approval_id": approval.approval_id,
            "fingerprint": fp,
            "fingerprint_short": fp[:12],
            "risk": decision.risk_level.value,
            "path": patch.path,
            "single_use": True,
            "ttl_seconds": APPROVAL_TTL_SECONDS,
        })
    return {
        "granted": granted,
        "count": len(granted),
        "note": "Approvals are single-use and bound to the exact fingerprint.",
    }


def execute(env, fingerprint=None, run_all=False, session=None):
    """Execute pending proposal(s) through the governed pipeline."""
    pending = load_pending(env.workspace)
    sessions = {
        r.get("fingerprint"): r.get("session", "")
        for r in pending
    }
    if fingerprint:
        pending = [
            r for r in pending
            if r.get("fingerprint", "").startswith(fingerprint)
        ]
    elif not run_all:
        pending = pending[:1]
    if not pending:
        return {
            "executed": False,
            "error": "no pending proposals",
            "terminal": None,
        }
    try:
        patches = [patch_from_record(r) for r in pending]
    except Exception as exc:
        return {
            "executed": False,
            "error": f"pending proposal could not be reconstructed: {exc}",
            "terminal": None,
        }
    test_targets, verification_profile = select_test_targets(
        env, [p.path for p in patches]
    )
    selected_sessions = sorted({
        r.get("session", "") for r in pending if r.get("session")
    })
    effective_session = session or (
        selected_sessions[0] if len(selected_sessions) == 1 else None
    )
    task_id = (
        f"tanuq-session:{effective_session}"
        if effective_session else "tanuq-agent"
    )
    result = env.pipeline.execute(
        WorkerResult(
            task_id=task_id,
            success=True,
            summary="tanuq agent execute",
            patches=tuple(patches),
        ),
        verify_paths=[str(env.workspace)],
        test_targets=test_targets,
        verification_profile=verification_profile,
    )
    state, stage = terminal_state(result)
    fingerprints = [p.fingerprint() for p in patches]
    related_sessions = sorted({
        sessions.get(fp, "") for fp in fingerprints
    } - {""})
    reason = None
    if result is not None:
        for patch_result in (result.patch_results or ()):
            if not patch_result.success and patch_result.message:
                reason = patch_result.message
                break
    if state == "VERIFIED" or (state == "DENIED" and stage in ("validation", "risk")):
        remove_pending(env.workspace, fingerprints)
    guidance = {
        "VERIFIED": "Change applied and verified; evidence recorded.",
        "ROLLED_BACK": "Verification failed — change was automatically rolled back.",
        "ROLLBACK_FAILED": "Rollback failed — investigate before continuing.",
        "DENIED": (
            "Approval missing or already used (single-use); run approve "
            "and re-execute." if stage == "approval"
            else "Proposal was permanently denied (out of scope or policy) "
                 "and removed; the agent must submit a corrected proposal."
        ),
        "FAILED": "Operation failed; see evidence journals.",
    }.get(state, "Operation did not reach a verified state.")
    return {
        "executed": True,
        "terminal": state,
        "failure_stage": stage,
        "apply_success": bool(result.apply_success) if result else False,
        "verification_passed": bool(result.verification_passed) if result else False,
        "verification_profile": verification_profile,
        "patches": [
            {"path": p.path, "fingerprint": p.fingerprint(), "fingerprint_short": p.fingerprint()[:12]}
            for p in patches
        ],
        "session": effective_session,
        "related_sessions": related_sessions,
        "reason": reason,
        "guidance": guidance,
        "pending_count": len(load_pending(env.workspace)),
    }
