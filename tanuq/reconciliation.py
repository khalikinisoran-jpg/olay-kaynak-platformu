"""E5 Reconciliation V1 — read-only state-consistency check (observation only).

Compares the journal-EVIDENCED content hash of every governed path
(ApplyOutcomeJournal intent records) against the ACTUAL disk bytes
(SHA-256 at read time).

Standing axioms (never merged, never violated):

    EXECUTION TRUTH != VERIFICATION RESULT != EVIDENCE RECORD
    evidence integrity != evidence truth
    reconciliation result != authorization
    reconciliation result != security verdict
    MATCH != secure
    CONTENT_MISMATCH != automatic block

Authority boundary: this module is OBSERVATION-ONLY. It grants no
authorization, creates no approvals, raises/lowers no risk, changes no
fingerprints, mutates no policy, executes nothing, writes nothing into
the evidence chain (or anywhere under .tanuq/), and never repairs.
It imports nothing from the governed pipeline / risk / approval
machinery (enforced by tests/e5_reconciliation_test.py).

Scope: journal-covered governed paths + pending paths ONLY. No
workspace-wide scanning; files never governed are outside this check
(coverage limitation, see agent_escape_e5_reconciliation_design_01.md
§4/§7). E5-4 verification blind spots (semantic/behavioral) are out of
scope by definition: MATCH means state consistency, NOT security.
"""
import hashlib
import json
import os
from datetime import datetime, timezone

STANDING_NOTE = (
    "Reconciliation = state consistency check (point-in-time). "
    "MATCH means: at read time, disk bytes matched the last evidenced hash. "
    "MATCH is NOT a security statement. CONTENT_MISMATCH is NOT an "
    "enforcement action - it is an observation for the human operator. "
    "Verification blind spots (E5-4) and out-of-channel runtime behavior "
    "are outside this check."
)

MATCH = "MATCH"
CONTENT_MISMATCH = "CONTENT_MISMATCH"
FILE_MISSING = "FILE_MISSING"
INDETERMINATE = "INDETERMINATE"
STALE_PENDING = "STALE_PENDING"
PARTIAL_EXECUTION_CANDIDATE = "PARTIAL_EXECUTION_CANDIDATE"
PENDING_NOTES = "PENDING_NOTES"
PROBE_ERROR = "PROBE_ERROR"

MISMATCH_CLASSES = (CONTENT_MISMATCH, FILE_MISSING)


def _norm(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _sha_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def reconcile_workspace(workspace):
    """Read-only reconciliation over journal-covered governed paths.

    Returns a plain dict (JSON-serializable). Never writes anything.
    """
    ws = _norm(workspace)
    observed_at = datetime.now(timezone.utc).isoformat()
    records = []
    summary = {"reconciled": 0, "pending_only": 0, "in_flight": 0,
               "errors": 0, "mismatches": 0}

    journal_intents = {}
    path_last_intent = {}
    journal_path = os.path.join(ws, ".tanuq", "data", "apply_journal.jsonl")
    if not os.path.exists(journal_path):
        records.append({"path": os.path.join(ws, ".tanuq", "data",
                         "apply_journal.jsonl"), "types": [PROBE_ERROR],
                        "detail": "apply journal not found"})
        summary["errors"] += 1
    else:
        with open(journal_path, encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    j = json.loads(line)
                except Exception as exc:
                    records.append({"path": journal_path, "line": i + 1,
                                    "types": [PROBE_ERROR],
                                    "detail": f"malformed journal line: {exc}"})
                    summary["errors"] += 1
                    continue
                if j.get("record_type") != "intent":
                    iid = j.get("intent_id")
                    if iid in journal_intents:
                        journal_intents[iid][j.get("record_type")] = True
                    continue
                iid = j.get("intent_id")
                journal_intents[iid] = j
                path_last_intent[_norm(j.get("path", ""))] = iid

    pending_by_path = {}
    pending_path = os.path.join(ws, ".tanuq", "data", "pending_proposals.json")
    if os.path.exists(pending_path):
        try:
            raw = json.load(open(pending_path, encoding="utf-8"))
            pending = raw if isinstance(raw, list) else raw.get("pending", [])
        except Exception as exc:
            records.append({"path": pending_path, "types": [PROBE_ERROR],
                            "detail": f"pending proposals unreadable: {exc}"})
            summary["errors"] += 1
        for p in pending:
            pending_by_path.setdefault(_norm(p.get("path", "")), []).append(p)

    governed = set(path_last_intent) | set(pending_by_path)
    for path in sorted(governed):
        rec = {"path": path, "types": [], "fingerprint": None,
               "terminal": None, "evidenced_sha256": None,
               "disk_sha256": None}
        iid = path_last_intent.get(path)
        intent = journal_intents.get(iid) if iid else None
        disk_exists = os.path.exists(path)
        try:
            rec["disk_sha256"] = _sha_file(path) if disk_exists else None
        except Exception as exc:
            rec["types"].append(PROBE_ERROR)
            rec["detail"] = f"disk read failed: {exc}"
            summary["errors"] += 1
            records.append(rec)
            continue
        if intent is None:
            rec["types"].append(PENDING_NOTES)
            rec["fingerprint"] = (pending_by_path[path][0].get("fingerprint")
                                  if pending_by_path.get(path) else None)
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
                    summary["mismatches"] += 1
                elif rec["disk_sha256"] == expected:
                    rec["types"].append(MATCH)
                    summary["reconciled"] += 1
                else:
                    rec["types"].append(CONTENT_MISMATCH)
                    summary["mismatches"] += 1
            else:
                rec["evidenced_sha256"] = None
        if path in pending_by_path:
            rec["types"].append(STALE_PENDING)
            if MATCH in rec["types"]:
                rec["types"].append(PARTIAL_EXECUTION_CANDIDATE)
        records.append(rec)

    return {"workspace": ws, "observed_at": observed_at,
            "records": records, "summary": summary,
            "note": STANDING_NOTE}


def render_human(result):
    """Human-readable CLI rendering (includes the mandatory standing note)."""
    s = result["summary"]
    lines = [
        "Tanuq reconciliation - state-consistency check (OBSERVATION ONLY)",
        f"  Observed at:  {result['observed_at']}",
        f"  Workspace:    {result['workspace']}",
        f"  Reconciled:   {s['reconciled']}  |  mismatches: {s['mismatches']}"
        f"  |  pending-only: {s['pending_only']}"
        f"  |  in-flight/interrupted: {s['in_flight']}"
        f"  |  probe errors: {s['errors']}",
        "",
    ]
    for rec in result["records"]:
        fp = (rec.get("fingerprint") or "-")[:12]
        lines.append(f"  {os.path.basename(rec['path'])}  [{','.join(rec['types'])}]"
                     f"  fp={fp}")
        if rec.get("detail"):
            lines.append(f"    detail: {rec['detail']}")
    if not result["records"]:
        lines.append("  No governed paths found in the journal.")
    lines.append("")
    lines.append(f"  NOTE: {result['note']}")
    return "\n".join(lines)
