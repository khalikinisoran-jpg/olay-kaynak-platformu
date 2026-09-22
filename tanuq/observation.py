"""E5/Semantic Observation V1 — read-only post-hoc observation projection.

STANDING AXIOMS:
    EXECUTION TRUTH != VERIFICATION RESULT != EVIDENCE RECORD
    evidence integrity != evidence truth
    Observation != Governance != Authorization != Execution
    MATCH != secure
    CONTENT_MISMATCH != automatic block

AUTHORITY BOUNDARY:
    This module:
    - CANNOT authorize
    - CANNOT create approvals
    - CANNOT change fingerprints
    - CANNOT execute
    - CANNOT write evidence
    - CANNOT modify risk/policy
    - CANNOT bypass governance
    - CANNOT lower risk
    - CANNOT map UNKNOWN to SAFE

    It READS journal + pending + disk state and RETURNS observation
    records. It writes NOTHING to .tanuq/ or the workspace.

    The evaluator (if provided) is INJECTED by the caller via the
    ``evaluator`` parameter. This module does not import, configure,
    or depend on any specific provider (JEV, LLM, rules engine, or
    human triage — all are valid evaluator implementations).

Import boundary: stdlib only (hashlib, json, os, datetime).
No imports from tanuq.*, simulation.*, or any governed-core module.
"""
import hashlib
import json
import os
from datetime import datetime, timezone

STANDING_NOTE = (
    "Observation = post-hoc read-only check (point-in-time). "
    "MATCH means: at read time, disk bytes matched the last evidenced hash. "
    "MATCH is NOT a security statement. CONTENT_MISMATCH is NOT an "
    "enforcement action. Observation != Governance != Authorization != "
    "Execution. UNKNOWN is never mapped to SAFE."
)

# --- E5-RECON state classes ---
MATCH = "MATCH"
CONTENT_MISMATCH = "CONTENT_MISMATCH"
FILE_MISSING = "FILE_MISSING"
INDETERMINATE = "INDETERMINATE"
STALE_PENDING = "STALE_PENDING"
PARTIAL_EXECUTION_CANDIDATE = "PARTIAL_EXECUTION_CANDIDATE"
PENDING_NOTES = "PENDING_NOTES"
PROBE_ERROR = "PROBE_ERROR"

# --- P1/P6/P7 result classes ---
FLAGGED = "flagged"
NOT_FLAGGED = "not_flagged"
ABSTAIN = "abstain"


def _norm(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _sha_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _read_journal(ws):
    """Parse apply_journal.jsonl → list of intent/terminal records."""
    journal_path = os.path.join(ws, ".tanuq", "data", "apply_journal.jsonl")
    if not os.path.exists(journal_path):
        return None
    records = []
    errors = []
    with open(journal_path, encoding="utf-8") as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except Exception as exc:
                errors.append({"line": i + 1, "detail": str(exc)})
    return {"records": records, "errors": errors}


def _read_pending(ws):
    """Parse pending_proposals.json → list of pending proposal dicts."""
    pending_path = os.path.join(ws, ".tanuq", "data", "pending_proposals.json")
    if not os.path.exists(pending_path):
        return []
    raw = json.load(open(pending_path, encoding="utf-8"))
    return raw if isinstance(raw, list) else raw.get("pending", [])


def observe_workspace(workspace, evaluator=None):
    """Read-only post-hoc observation over a governed workspace.

    Args:
        workspace: absolute path to the governed workspace.
        evaluator: optional callable(proposal_fields: dict) -> dict.
            The evaluator receives {"path", "action", "reason", "old_content",
            "new_content"} and returns {"P1": {...}, "P6": {...}, "P7": {...}}.
            If None, only E5-RECON state-consistency records are produced.

    Returns:
        A JSON-serializable dict. Writes NOTHING to .tanuq/ or the
        workspace. The caller decides where to store the output.
    """
    ws = _norm(workspace)
    observed_at = datetime.now(timezone.utc).isoformat()
    records = []
    summary = {"governed_paths": 0, "matches": 0, "mismatches": 0,
               "file_missing": 0, "in_flight": 0, "pending_only": 0,
               "partial_candidates": 0, "probe_errors": 0,
               "evaluator_observations": 0}

    # --- E5-RECON: state-consistency records ---
    jr = _read_journal(ws)
    if jr is None:
        records.append({"primitive_id": "E5-RECON",
                        "types": [PROBE_ERROR],
                        "detail": "apply journal not found"})
        summary["probe_errors"] += 1
    else:
        if jr["errors"]:
            for err in jr["errors"]:
                records.append({"primitive_id": "E5-RECON",
                                "types": [PROBE_ERROR], "detail": err})
                summary["probe_errors"] += 1
        intents = {}       # intent_id -> intent record
        path_last = {}     # norm(path) -> intent_id (last)
        for rec in jr["records"]:
            if rec.get("record_type") == "intent":
                iid = rec["intent_id"]
                intents[iid] = rec
                path_last[_norm(rec["path"])] = iid
            else:
                iid = rec.get("intent_id")
                if iid in intents:
                    intents[iid][rec["record_type"]] = True

        pending = _read_pending(ws)
        pending_by_path = {}
        for p in pending:
            pending_by_path.setdefault(_norm(p.get("path", "")), []).append(p)

        governed = set(path_last) | set(pending_by_path)
        summary["governed_paths"] = len(governed)

        for norm_path in sorted(governed):
            rec = {"primitive_id": "E5-RECON", "path": norm_path,
                   "types": [], "fingerprint": None, "terminal": None,
                   "evidenced_sha256": None, "disk_sha256": None}
            iid = path_last.get(norm_path)
            intent = intents.get(iid) if iid else None
            disk_exists = os.path.exists(norm_path)
            disk_sha = _sha_file(norm_path) if disk_exists else None
            rec["disk_sha256"] = disk_sha

            if intent is None:
                rec["types"].append(PENDING_NOTES)
                fp = pending_by_path[norm_path][0].get("fingerprint", "") \
                    if pending_by_path.get(norm_path) else None
                rec["fingerprint"] = fp
                summary["pending_only"] += 1
            else:
                rec["fingerprint"] = intent.get("patch_fingerprint")
                if intent.get("rolled_back"):
                    expected = intent.get("old_content_hash")
                    rec["terminal"] = "rolled_back"
                elif intent.get("applied"):
                    expected = intent.get("new_content_hash")
                    rec["terminal"] = "applied"
                else:
                    expected = None
                    rec["terminal"] = "in_flight_or_interrupted"
                    rec["types"].append(INDETERMINATE)
                    summary["in_flight"] += 1
                if expected is not None:
                    rec["evidenced_sha256"] = expected
                    if not disk_exists:
                        rec["types"].append(FILE_MISSING)
                        summary["file_missing"] += 1
                    elif disk_sha == expected:
                        rec["types"].append(MATCH)
                        summary["matches"] += 1
                    else:
                        rec["types"].append(CONTENT_MISMATCH)
                        summary["mismatches"] += 1
            if norm_path in pending_by_path:
                rec["types"].append(STALE_PENDING)
                if MATCH in rec["types"]:
                    rec["types"].append(PARTIAL_EXECUTION_CANDIDATE)
            records.append(rec)

    # --- P1/P6/P7: evaluator observations (if evaluator injected) ---
    if evaluator is not None:
        for norm_path in sorted(governed):
            disk_path = norm_path
            if not os.path.exists(disk_path):
                continue
            content = open(disk_path, "rb").read()
            # find the latest reason/action from journal or pending
            reason = ""
            action = "modify"
            for p in pending:
                if _norm(p.get("path", "")) == norm_path:
                    reason = p.get("reason", "")
                    action = p.get("action", "modify")
                    break
            proposal = {"path": disk_path, "action": action,
                        "reason": reason, "content": content.decode("utf-8", errors="replace")}
            try:
                obs = evaluator(proposal)
                for pid in ("P1", "P6", "P7"):
                    if pid in obs:
                        rec = {"primitive_id": pid, "path": disk_path,
                               "result": obs[pid],
                               "unknown_count": sum(1 for v in obs[pid].values() if v == "U"),
                               "provenance": obs.get("provenance", {}),
                               "timestamp": observed_at}
                        records.append(rec)
                        summary["evaluator_observations"] += 1
            except Exception as exc:
                records.append({"primitive_id": "E5-RECON", "path": disk_path,
                                "types": [PROBE_ERROR],
                                "detail": f"evaluator failed: {exc}"})
                summary["probe_errors"] += 1

    return {"workspace": ws, "observed_at": observed_at,
            "records": records, "summary": summary, "note": STANDING_NOTE}


def render_human(result):
    """Human-readable CLI rendering."""
    s = result["summary"]
    lines = [
        "Tanuq observation - post-hoc read-only check (OBSERVATION ONLY)",
        f"  Observed at:  {result['observed_at']}",
        f"  Workspace:    {result['workspace']}",
        f"  Governed paths: {s['governed_paths']}"
        f"  |  matches: {s['matches']}  |  mismatches: {s['mismatches']}"
        f"  |  pending-only: {s['pending_only']}"
        f"  |  in-flight: {s['in_flight']}"
        f"  |  partial candidates: {s['partial_candidates']}"
        f"  |  probe errors: {s['probe_errors']}"
        f"  |  evaluator observations: {s['evaluator_observations']}",
        "",
    ]
    for rec in result["records"]:
        path_short = os.path.basename(rec.get("path", rec.get("detail", "")))
        types = ",".join(rec.get("types", []))
        lines.append(f"  {path_short}  [{types}]")
        if rec.get("detail"):
            lines.append(f"    detail: {rec['detail']}")
    if not result["records"]:
        lines.append("  No governed paths found.")
    lines.append("")
    lines.append(f"  NOTE: {result['note']}")
    return "\n".join(lines)
