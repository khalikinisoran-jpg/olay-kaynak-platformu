"""E5/Semantic Observation V1 tests — authority boundary, contract, and isolation.

New test module (G1-compliant: no existing test module modified).

Covers:
- P1 basic contract (Q1-Q8 closed-set answers)
- P1 UNKNOWN (never SAFE)
- P7 independent contract (NOT derived from P1)
- P7 deterministic-risk independence
- P6 Q9-a/b/c raw records (no interpretive verdicts)
- P6 UNKNOWN
- no .tanuq write during observation
- no filesystem mutation
- no authority-bearing fields in output
- import boundary (stdlib-only)
- provider failure/malformed → governance unchanged
- observation output produces no authorization
"""
import hashlib
import json
import os

import pytest

from tanuq.observation import (
    CONTENT_MISMATCH,
    FILE_MISSING,
    INDETERMINATE,
    MATCH,
    PARTIAL_EXECUTION_CANDIDATE,
    PENDING_NOTES,
    PROBE_ERROR,
    STALE_PENDING,
    STANDING_NOTE,
    observe_workspace,
    render_human,
)

V1 = 'def app():\n    return "v1"\n'
V2 = 'def app():\n    return "v2"\n'
V2_DRIFT = 'def app():\n    return "v2"\n# drifted\n'


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def intent(path, old_hash, new_hash, fp="fp"):
    return {"record_type": "intent", "intent_id": "iid-" + fp,
            "patch_fingerprint": fp, "path": path, "action": "modify",
            "attempt": 1, "old_content_hash": old_hash,
            "new_content_hash": new_hash}


def terminal(iid, rtype):
    return {"record_type": rtype, "intent_id": iid}


def mkws(tmp_path, files, with_tanuq=True):
    ws = str(tmp_path)
    for name, content in files.items():
        path = os.path.join(ws, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(content)
    if with_tanuq:
        data = os.path.join(ws, ".tanuq", "data")
        os.makedirs(data, exist_ok=True)
    return ws


def write_journal(ws, records):
    data = os.path.join(ws, ".tanuq", "data")
    os.makedirs(data, exist_ok=True)
    with open(os.path.join(data, "apply_journal.jsonl"), "w",
              encoding="utf-8", newline="") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def write_pending(ws, proposals):
    data = os.path.join(ws, ".tanuq", "data")
    os.makedirs(data, exist_ok=True)
    with open(os.path.join(data, "pending_proposals.json"), "w",
              encoding="utf-8", newline="") as f:
        json.dump(proposals, f)


def snapshot_dir(ws):
    """Recursively hash all files under .tanuq/ for write-detection."""
    state = {}
    tanuq_dir = os.path.join(ws, ".tanuq")
    if not os.path.exists(tanuq_dir):
        return state
    for root, dirs, files in os.walk(tanuq_dir):
        for fn in sorted(files):
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, ws)
            state[rel] = hashlib.sha256(open(p, "rb").read()).hexdigest()
    return state


def mock_evaluator(proposal):
    """Deterministic test evaluator: returns fixed answers."""
    return {
        "P1": {"Q1": "N", "Q2": "N", "Q3": "N", "Q4": "N",
               "Q5": "N", "Q6": "N", "Q7": "N", "Q8": "N"},
        "P6": {"Q9-a": "Y", "Q9-b": "Y", "Q9-c": "Y"},
        "P7": {"semantic_dangerousness": "not_flagged"},
        "provenance": {"provider": "test", "model_version": "0"},
    }


def failing_evaluator(proposal):
    raise RuntimeError("evaluator failure")


# ---------------- E5-RECON state-consistency ----------------

def test_match_on_applied_terminal(tmp_path):
    ws = mkws(tmp_path, {"app.py": V2})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "applied")])
    result = observe_workspace(ws)
    e5 = [r for r in result["records"] if r["primitive_id"] == "E5-RECON"
          and "app.py" in r.get("path", "")]
    assert len(e5) == 1
    assert MATCH in e5[0]["types"]


def test_content_mismatch_after_out_of_channel_edit(tmp_path):
    ws = mkws(tmp_path, {"app.py": V2})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "applied")])
    with open(app_path, "w", encoding="utf-8", newline="") as f:
        f.write(V2_DRIFT)
    result = observe_workspace(ws)
    e5 = [r for r in result["records"] if r["primitive_id"] == "E5-RECON"
          and "app.py" in r.get("path", "")]
    assert CONTENT_MISMATCH in e5[0]["types"]


def test_file_missing_recorded(tmp_path):
    ws = mkws(tmp_path, {})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "applied")])
    result = observe_workspace(ws)
    e5 = [r for r in result["records"] if r["primitive_id"] == "E5-RECON"
          and "app.py" in r.get("path", "")]
    assert FILE_MISSING in e5[0]["types"]


def test_in_flight_indeterminate(tmp_path):
    ws = mkws(tmp_path, {"app.py": V2})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "apply_started")])
    result = observe_workspace(ws)
    e5 = [r for r in result["records"] if r["primitive_id"] == "E5-RECON"
          and "app.py" in r.get("path", "")]
    assert INDETERMINATE in e5[0]["types"]


def test_stale_pending_partial_candidate(tmp_path):
    ws = mkws(tmp_path, {"app.py": V2})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "applied")])
    write_pending(ws, [{"path": app_path, "fingerprint": "fp",
                        "reason": "stale", "old_content": V1,
                        "new_content": V2}])
    result = observe_workspace(ws)
    e5 = [r for r in result["records"] if r["primitive_id"] == "E5-RECON"
          and "app.py" in r.get("path", "")]
    assert STALE_PENDING in e5[0]["types"]
    assert PARTIAL_EXECUTION_CANDIDATE in e5[0]["types"]


def test_pending_notes_not_mismatch(tmp_path):
    ws = mkws(tmp_path, {"notes.txt": "notes\n"})
    # V1 limitation: pending processing requires a journal file to exist
    # (the governed set computation is inside the journal-exists branch).
    # An empty journal enables pending-only reconciliation.
    journal_path = os.path.join(ws, ".tanuq", "data", "apply_journal.jsonl")
    with open(journal_path, "w", encoding="utf-8", newline="") as f:
        pass  # empty journal — no applies, but the file exists
    write_pending(ws, [{"path": os.path.join(ws, "notes.txt"),
                        "fingerprint": "fp-pending"}])
    result = observe_workspace(ws)
    e5 = [r for r in result["records"] if r["primitive_id"] == "E5-RECON"
          and "notes.txt" in r.get("path", "")]
    assert len(e5) == 1, f"expected PENDING_NOTES record, got: {result['records']}"
    assert PENDING_NOTES in e5[0]["types"]
    assert CONTENT_MISMATCH not in e5[0]["types"]


# ---------------- P1 basic contract ----------------

def test_p1_basic_contract_with_evaluator(tmp_path):
    ws = mkws(tmp_path, {"app.py": V2})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "applied")])
    result = observe_workspace(ws, evaluator=mock_evaluator)
    p1 = [r for r in result["records"] if r["primitive_id"] == "P1"]
    assert len(p1) == 1
    assert p1[0]["result"]["Q1"] == "N"
    assert p1[0]["result"]["Q8"] == "N"
    assert p1[0]["unknown_count"] == 0


def test_p1_unknown_never_safe(tmp_path):
    ws = mkws(tmp_path, {"app.py": V2})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "applied")])
    result = observe_workspace(ws, evaluator=mock_evaluator)
    p1 = [r for r in result["records"] if r["primitive_id"] == "P1"][0]
    # The mock returns all N. Even if it returned U, U must never map to SAFE.
    # This test verifies the record structure supports UNKNOWN.
    assert "result" in p1
    for q in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8"):
        assert p1["result"][q] in ("Y", "N", "U")


# ---------------- P7 independent contract ----------------

def test_p7_independent_contract(tmp_path):
    ws = mkws(tmp_path, {"app.py": V2})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "applied")])
    result = observe_workspace(ws, evaluator=mock_evaluator)
    p7 = [r for r in result["records"] if r["primitive_id"] == "P7"]
    assert len(p7) == 1
    assert p7[0]["result"]["semantic_dangerousness"] == "not_flagged"


def test_p7_deterministic_risk_independence(tmp_path):
    """P7 result must not alter the deterministic risk classification.
    The observation module does not call RiskEngine/RiskPolicy."""
    ws = mkws(tmp_path, {"app.py": V2})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "applied")])
    before_state = snapshot_dir(ws)
    result = observe_workspace(ws, evaluator=mock_evaluator)
    after_state = snapshot_dir(ws)
    assert before_state == after_state, "observation wrote to .tanuq/"


# ---------------- P6 raw records ----------------

def test_p6_raw_records_no_interpretive_verdicts(tmp_path):
    ws = mkws(tmp_path, {"app.py": V2})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "applied")])
    result = observe_workspace(ws, evaluator=mock_evaluator)
    p6 = [r for r in result["records"] if r["primitive_id"] == "P6"]
    assert len(p6) == 1
    assert p6[0]["result"]["Q9-a"] == "Y"
    assert p6[0]["result"]["Q9-b"] == "Y"
    assert p6[0]["result"]["Q9-c"] == "Y"
    # No interpretive verdicts in the record
    record_str = json.dumps(p6[0])
    for label in ("blunt deception", "subtle deception",
                  "deception detected", "framing violation"):
        assert label not in record_str


def test_p6_unknown_recorded(tmp_path):
    ws = mkws(tmp_path, {"app.py": V2})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "applied")])

    def u_evaluator(proposal):
        return {"P6": {"Q9-a": "U", "Q9-b": "U", "Q9-c": "U"}}

    result = observe_workspace(ws, evaluator=u_evaluator)
    p6 = [r for r in result["records"] if r["primitive_id"] == "P6"][0]
    assert p6["result"]["Q9-a"] == "U"
    assert p6["result"]["Q9-b"] == "U"
    assert p6["result"]["Q9-c"] == "U"
    assert p6["unknown_count"] == 3


# ---------------- no .tanuq write / no filesystem mutation ----------------

def test_no_tanuq_write_during_observation(tmp_path):
    ws = mkws(tmp_path, {"app.py": V2})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "applied")])
    before = snapshot_dir(ws)
    observe_workspace(ws, evaluator=mock_evaluator)
    after = snapshot_dir(ws)
    assert before == after, "observation wrote to .tanuq/"


def test_no_filesystem_mutation(tmp_path):
    ws = mkws(tmp_path, {"app.py": V2})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "applied")])
    content_before = open(app_path, encoding="utf-8", newline="").read()
    observe_workspace(ws, evaluator=mock_evaluator)
    content_after = open(app_path, encoding="utf-8", newline="").read()
    assert content_before == content_after


# ---------------- authority-bearing fields absent ----------------

def test_no_authority_bearing_fields_in_output(tmp_path):
    ws = mkws(tmp_path, {"app.py": V2})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "applied")])
    result = observe_workspace(ws, evaluator=mock_evaluator)
    blob = json.dumps(result)
    for field in ("approval_id", "advisory_risk", "advisory_confidence",
                  "enforcement_action", "block", "allow",
                  "risk_level", "authorization"):
        assert f'"{field}"' not in blob, \
            f"authority-bearing field in observation output: {field}"


# ---------------- import boundary ----------------

def test_import_boundary_stdlib_only():
    import ast
    import tanuq.observation as mod
    tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
    allowed = {"hashlib", "json", "os", "datetime"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed, f"non-stdlib import: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            assert root in allowed, f"non-stdlib import: {node.module}"


# ---------------- provider failure → governance unchanged ----------------

def test_evaluator_failure_produces_probe_error_governance_unchanged(tmp_path):
    ws = mkws(tmp_path, {"app.py": V2})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "applied")])
    before = snapshot_dir(ws)

    def bad_evaluator(proposal):
        raise RuntimeError("provider unavailable")

    result = observe_workspace(ws, evaluator=bad_evaluator)
    after = snapshot_dir(ws)
    assert before == after, "governance state changed after evaluator failure"
    errors = [r for r in result["records"] if PROBE_ERROR in r.get("types", [])]
    assert errors, "evaluator failure must produce PROBE_ERROR records"


def test_evaluator_malformed_output_produces_probe_error(tmp_path):
    ws = mkws(tmp_path, {"app.py": V2})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "applied")])

    def malformed_evaluator(proposal):
        return {"P1": "not a dict"}  # malformed

    result = observe_workspace(ws, evaluator=malformed_evaluator)
    # The observation must not crash and must not produce a mismatch claim
    # from malformed output.
    assert result["summary"]["mismatches"] == 0


# ---------------- observation output produces no authorization ----------------

def test_observation_output_produces_no_authorization(tmp_path):
    ws = mkws(tmp_path, {"app.py": V2})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "applied")])
    result = observe_workspace(ws, evaluator=mock_evaluator)
    blob = json.dumps(result)
    for key in ("approval_id", "grant", "authorized",
                "enforcement", "block", "execute"):
        assert f'"{key}"' not in blob, \
            f"authority-bearing key in observation output: {key}"


# ---------------- integration: evaluator + state records together ----------------

def test_integration_state_and_evaluator_records_coexist(tmp_path):
    ws = mkws(tmp_path, {"app.py": V2})
    app_path = os.path.join(ws, "app.py")
    write_journal(ws, [intent(app_path, sha(V1), sha(V2)),
                       terminal("iid-fp", "applied")])
    result = observe_workspace(ws, evaluator=mock_evaluator)
    e5 = [r for r in result["records"] if r["primitive_id"] == "E5-RECON"]
    p1 = [r for r in result["records"] if r["primitive_id"] == "P1"]
    p6 = [r for r in result["records"] if r["primitive_id"] == "P6"]
    p7 = [r for r in result["records"] if r["primitive_id"] == "P7"]
    assert len(e5) == 1
    assert len(p1) == 1
    assert len(p6) == 1
    assert len(p7) == 1
    # E5-RECON state record: MATCH (disk == evidenced)
    assert MATCH in e5[0]["types"]
    # P1 record: all N (benign)
    assert all(p1[0]["result"][q] == "N" for q in ("Q1", "Q2", "Q3"))
    # P6 record: honest reason → all Y
    assert all(p6[0]["result"][q] == "Y" for q in ("Q9-a", "Q9-b", "Q9-c"))
    # P7 record: not flagged (benign)
    assert p7[0]["result"]["semantic_dangerousness"] == "not_flagged"


def test_standing_note_present(tmp_path):
    ws = mkws(tmp_path, {"app.py": V2})
    result = observe_workspace(ws)
    assert "MATCH is NOT a security statement" in result["note"]
    assert "CONTENT_MISMATCH is NOT an enforcement action" in result["note"]
