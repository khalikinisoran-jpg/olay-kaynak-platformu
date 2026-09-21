"""E5 Reconciliation V1 tests (Design-01 §24 / Boundary-01 §7).

New test module (G1-compliant: no existing test module modified).

Covers: result-class rule units (MATCH / CONTENT_MISMATCH / FILE_MISSING /
INDETERMINATE / STALE_PENDING / PARTIAL_EXECUTION_CANDIDATE /
PENDING_NOTES / PROBE_ERROR), hash convention, rolled_back old-hash
semantics, last-intent-wins, malformed-journal boundary, output contract
(no file contents; standing note), authority boundary (no governed-core
imports, no .tanuq writes), privacy, and a real-CLI integration pass.
"""
import hashlib
import json
import os
import subprocess
import sys

import pytest

from tanuq.reconciliation import (
    CONTENT_MISMATCH,
    FILE_MISSING,
    INDETERMINATE,
    MATCH,
    PARTIAL_EXECUTION_CANDIDATE,
    PENDING_NOTES,
    PROBE_ERROR,
    STALE_PENDING,
    reconcile_workspace,
    render_human,
    STANDING_NOTE,
)

V1 = 'def app():\n    return "v1"\n'
V2 = 'def app():\n    return "v2"\n'
V2_DRIFT = 'def app():\n    return "v2"\n# drifted\n'


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def intent(path, old, new, fingerprint="fp-test-0001"):
    return {"record_type": "intent", "intent_id": "iid-" + fingerprint,
            "patch_fingerprint": fingerprint, "path": path, "action": "modify",
            "attempt": 1, "old_content_hash": sha(old),
            "new_content_hash": sha(new)}


def jrec(iid, rtype):
    return {"record_type": rtype, "intent_id": iid}


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


def write_file(ws, name, content):
    path = os.path.join(ws, name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(content)
    return os.path.join(ws, name)


def types_of(result, name):
    return [r for r in result["records"] if r["path"].endswith(name)]


# ---------------- rule units ----------------

def test_match_on_applied_terminal(tmp_path):
    ws = str(tmp_path)
    write_file(ws, "app.py", V2)
    write_journal(ws, [intent(os.path.join(ws, "app.py"), V1, V2),
                       jrec("iid-fp-test-0001", "applied")])
    result = reconcile_workspace(ws)
    row = types_of(result, "app.py")[0]
    assert MATCH in row["types"]
    assert CONTENT_MISMATCH not in row["types"]
    assert row["evidenced_sha256"] == sha(V2)
    assert row["disk_sha256"] == sha(V2)


def test_content_mismatch_after_out_of_channel_edit(tmp_path):
    ws = str(tmp_path)
    write_file(ws, "app.py", V2_DRIFT)
    write_journal(ws, [intent(os.path.join(ws, "app.py"), V1, V2),
                       jrec("iid-fp-test-0001", "applied")])
    result = reconcile_workspace(ws)
    row = types_of(result, "app.py")[0]
    assert CONTENT_MISMATCH in row["types"]
    assert MATCH not in row["types"]
    assert row["evidenced_sha256"] == sha(V2)
    assert row["disk_sha256"] == sha(V2_DRIFT)


def test_file_missing_recorded(tmp_path):
    ws = str(tmp_path)
    write_journal(ws, [intent(os.path.join(ws, "app.py"), V1, V2),
                       jrec("iid-fp-test-0001", "applied")])
    result = reconcile_workspace(ws)
    row = types_of(result, "app.py")[0]
    assert FILE_MISSING in row["types"]


def test_rolled_back_with_disk_still_new_is_mismatch(tmp_path):
    # rolled_back terminal: evidenced content = OLD content (V1).
    # Disk still holding the NEW content (V2) means the rollback did not
    # actually restore -> CONTENT_MISMATCH (genuine detection case).
    ws = str(tmp_path)
    write_file(ws, "app.py", V2)
    write_journal(ws, [intent(os.path.join(ws, "app.py"), V1, V2),
                       jrec("iid-fp-test-0001", "applied"),
                       jrec("iid-fp-test-0001", "rollback_started"),
                       jrec("iid-fp-test-0001", "rolled_back")])
    result = reconcile_workspace(ws)
    row = types_of(result, "app.py")[0]
    assert CONTENT_MISMATCH in row["types"]
    assert row["evidenced_sha256"] == sha(V1)


def test_rolled_back_restores_old_content_exact(tmp_path):
    ws = str(tmp_path)
    write_file(ws, "app.py", V1)  # rollback restored V1 (the old content)
    write_journal(ws, [intent(os.path.join(ws, "app.py"), V1, V2),
                       jrec("iid-fp-test-0001", "applied"),
                       jrec("iid-fp-test-0001", "rollback_started"),
                       jrec("iid-fp-test-0001", "rolled_back")])
    result = reconcile_workspace(ws)
    row = types_of(result, "app.py")[0]
    assert MATCH in row["types"]
    assert row["evidenced_sha256"] == sha(V1)


def test_rolled_back_mismatch_detected(tmp_path):
    ws = str(tmp_path)
    write_file(ws, "app.py", "def app():\n    return 'neither'\n")
    write_journal(ws, [intent(os.path.join(ws, "app.py"), V1, V2),
                       jrec("iid-fp-test-0001", "applied"),
                       jrec("iid-fp-test-0001", "rollback_started"),
                       jrec("iid-fp-test-0001", "rolled_back")])
    result = reconcile_workspace(ws)
    row = types_of(result, "app.py")[0]
    assert CONTENT_MISMATCH in row["types"]


def test_apply_started_without_terminal_is_indeterminate(tmp_path):
    ws = str(tmp_path)
    write_file(ws, "app.py", V2)  # in-flight/interrupted: disk state indeterminate
    write_journal(ws, [intent(os.path.join(ws, "app.py"), V1, V2),
                       jrec("iid-fp-test-0001", "apply_started")])
    result = reconcile_workspace(ws)
    row = types_of(result, "app.py")[0]
    assert INDETERMINATE in row["types"]
    assert CONTENT_MISMATCH not in row["types"]
    assert MATCH not in row["types"]


def test_stale_pending_partial_execution_candidate(tmp_path):
    ws = str(tmp_path)
    write_file(ws, "app.py", V2)
    write_journal(ws, [intent(os.path.join(ws, "app.py"), V1, V2),
                       jrec("iid-fp-test-0001", "applied")])
    write_pending(ws, [{"path": os.path.join(ws, "app.py"),
                        "fingerprint": "fp-test-0001"}])
    result = reconcile_workspace(ws)
    row = types_of(result, "app.py")[0]
    assert MATCH in row["types"]
    assert STALE_PENDING in row["types"]
    assert PARTIAL_EXECUTION_CANDIDATE in row["types"]


def test_pending_notes_is_not_a_mismatch(tmp_path):
    ws = str(tmp_path)
    write_file(ws, "notes.txt", "notes\n")
    write_pending(ws, [{"path": os.path.join(ws, "notes.txt"),
                        "fingerprint": "fp-pending"}])
    result = reconcile_workspace(ws)
    row = types_of(result, "notes.txt")[0]
    assert PENDING_NOTES in row["types"]
    assert CONTENT_MISMATCH not in row["types"]


def test_last_intent_wins(tmp_path):
    ws = str(tmp_path)
    V3 = 'def app():\n    return "v3"\n'
    write_file(ws, "app.py", V3)
    write_journal(ws, [intent(os.path.join(ws, "app.py"), V1, V2, "fp-a"),
                       jrec("iid-fp-a", "applied"),
                       intent(os.path.join(ws, "app.py"), V2, V3, "fp-b"),
                       jrec("iid-fp-b", "applied")])
    result = reconcile_workspace(ws)
    row = types_of(result, "app.py")[0]
    assert MATCH in row["types"]
    assert row["evidenced_sha256"] == sha(V3)


def test_malformed_journal_line_is_probe_error_not_mismatch(tmp_path):
    ws = str(tmp_path)
    write_file(ws, "app.py", V2)
    data = os.path.join(ws, ".tanuq", "data")
    os.makedirs(data, exist_ok=True)
    good = json.dumps(intent(os.path.join(ws, "app.py"), V1, V2))
    with open(os.path.join(data, "apply_journal.jsonl"), "w",
              encoding="utf-8", newline="") as f:
        f.write("{malformed json line\n")
        f.write(good + "\n")
    result = reconcile_workspace(ws)
    err = [r for r in result["records"] if PROBE_ERROR in r["types"]]
    assert err, "malformed line must produce a PROBE_ERROR record"
    summary = result["summary"]
    assert summary["errors"] >= 1
    assert summary["mismatches"] == 0  # PROBE_ERROR is never a mismatch claim


# ---------------- output contract / privacy / standing note ----------------

def test_json_output_contract_and_privacy(tmp_path):
    ws = str(tmp_path)
    secret_free = V2
    write_file(ws, "app.py", V2_DRIFT)
    write_journal(ws, [intent(os.path.join(ws, "app.py"), V1, V2),
                       jrec("iid-fp-test-0001", "applied")])
    result = reconcile_workspace(ws)
    blob = json.dumps(result)
    assert "types" in blob and "MATCH" in blob
    # privacy: no file CONTENT in the output (only hashes/paths/types)
    assert V2 not in blob
    assert V2_DRIFT not in blob
    assert V1 not in blob
    assert result["note"] == STANDING_NOTE


def test_human_output_carries_standing_note(tmp_path):
    ws = str(tmp_path)
    write_file(ws, "app.py", V2)
    write_journal(ws, [intent(os.path.join(ws, "app.py"), V1, V2),
                       jrec("iid-fp-test-0001", "applied")])
    result = reconcile_workspace(ws)
    human = render_human(result)
    assert "MATCH is NOT a security statement" in human
    assert "CONTENT_MISMATCH is NOT an enforcement action" in human
    assert "OBSERVATION ONLY" in human


# ---------------- authority boundary ----------------

def test_authority_boundary_no_governed_core_imports():
    import ast
    import tanuq.reconciliation as mod
    src = open(mod.__file__, encoding="utf-8").read()
    tree = ast.parse(src)
    allowed = {"hashlib", "json", "os", "datetime"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                assert root in allowed, f"non-stdlib import in reconciliation: {alias.name}"
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            assert root in allowed, f"non-stdlib import in reconciliation: {node.module}"
    # no governed-core vocabulary in the module at all
    forbidden = ("simulation", "WorkerActionPipeline", "FileApplier",
                 "ApplyAuthorization", "ApprovalStore", "ApprovalLedger",
                 "GovernanceEvaluator", "risk_engine", "risk_policy",
                 "coordinator", "subprocess", "socket")
    for token in forbidden:
        assert token not in src, f"authority boundary violation: {token}"


def test_no_tanuq_writes_during_reconciliation(tmp_path):
    ws = str(tmp_path)
    write_file(ws, "app.py", V2)
    write_journal(ws, [intent(os.path.join(ws, "app.py"), V1, V2),
                       jrec("iid-fp-test-0001", "applied")])
    data = os.path.join(ws, ".tanuq", "data")

    def snapshot():
        state = {}
        for fn in os.listdir(data):
            p = os.path.join(data, fn)
            if os.path.isfile(p):
                state[fn] = hashlib.sha256(open(p, "rb").read()).hexdigest()
        return state

    before = snapshot()
    reconcile_workspace(ws)
    assert snapshot() == before, "reconciliation must never write into .tanuq/"


# ---------------- integration (real CLI) ----------------

def _cli(ws, args, stdin=None):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    co = os.path.join(ws, "_cli_out.txt")
    fin = ""
    if stdin:
        sp = os.path.join(ws, "_cli_in.json")
        with open(sp, "w", encoding="utf-8", newline="") as f:
            f.write(stdin)
        fin = f' < "{sp}"'
    qargs = " ".join(f'"{a}"' for a in args)
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cmd = f'"{sys.executable}" -m tanuq {qargs}{fin} > "{co}" 2> "{os.path.join(ws, "_cli_err.txt")}"'
    p = subprocess.run(cmd, shell=True, cwd=repo, env=env)
    out = open(co, "rb").read().decode("utf-8", errors="replace")
    return p.returncode, out


def test_integration_real_cli_match_then_drift(tmp_path):
    ws = str(tmp_path)
    write_file(ws, "app.py", V1)
    code, out = _cli(ws, ["init", "--workspace", ws, "--yes"])
    assert code == 0
    code, out = _cli(ws, ["propose", "--workspace", ws, "--stdin-json", "--json"],
                     json.dumps({"path": os.path.join(ws, "app.py"),
                                 "action": "modify",
                                 "reason": "reconciliation integration",
                                 "old_content": V1,
                                 "new_content": V2}))
    assert code == 0
    fp = json.loads(out)["proposals"][0]["fingerprint"]
    code, out = _cli(ws, ["execute", "--workspace", ws,
                          "--fingerprint", fp])
    assert "VERIFIED" in out
    # governed state -> MATCH
    result = reconcile_workspace(ws)
    row = [r for r in result["records"] if r["path"].endswith("app.py")][0]
    assert MATCH in row["types"]
    # out-of-channel edit -> CONTENT_MISMATCH (E5-1 closed for journal paths)
    with open(os.path.join(ws, "app.py"), "a", encoding="utf-8", newline="") as f:
        f.write("# drifted\n")
    result = reconcile_workspace(ws)
    row = [r for r in result["records"] if r["path"].endswith("app.py")][0]
    assert CONTENT_MISMATCH in row["types"]
    # CLI surface
    code, out = _cli(ws, ["reconcile", "--workspace", ws, "--json"])
    assert code == 0
    parsed = json.loads(out)
    assert parsed["summary"]["mismatches"] >= 1
    assert "MATCH is NOT a security statement" in parsed["note"]
    code, out = _cli(ws, ["reconcile", "--workspace", ws])
    assert "OBSERVATION ONLY" in out


def test_cli_registers_reconcile_subcommand():
    import tanuq.cli as cli_mod
    src = open(cli_mod.__file__, encoding="utf-8").read()
    assert 'add_parser(\n        "reconcile"' in src or 'add_parser("reconcile"' in src
