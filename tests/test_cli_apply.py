import subprocess
import sys
import tempfile
from pathlib import Path

import pathlib

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

def _run_cli(args, workspace):
    cmd = [sys.executable, "agent_run.py"] + args
    # ensure workspace is passed already
    result = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    return result

def _read(p: Path):
    return p.read_text(encoding="utf-8")

def test_cli_low_risk_success():
    ws = Path(tempfile.mkdtemp(prefix="cli_low_"))
    target = ws / "demo.txt"
    target.write_text("hello\n", encoding="utf-8")
    res = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", "hello fixed\n", "--workspace", str(ws)], ws)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "Risk: LOW" in res.stdout
    assert "Approval required: False" in res.stdout
    assert "Apply success: True" in res.stdout
    assert "Verification passed: True" in res.stdout
    assert "Terminal state: VERIFIED" in res.stdout
    assert _read(target) == "hello fixed\n"
    journal = ws / ".cli_platform" / "apply_journal.jsonl"
    assert journal.exists()
    assert "verified" in journal.read_text(encoding="utf-8")

def test_cli_high_risk_denied_without_approval():
    ws = Path(tempfile.mkdtemp(prefix="cli_high_denied_"))
    target = ws / "demo.txt"
    target.write_text("hello\n", encoding="utf-8")
    res = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", 'api_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n', "--workspace", str(ws)], ws)
    assert res.returncode != 0
    assert "Risk: HIGH" in res.stdout
    assert "Approval required: True" in res.stdout
    assert "Failure stage: approval" in res.stdout
    assert "Apply success: False" in res.stdout
    assert _read(target) == "hello\n"
    journal = ws / ".cli_platform" / "apply_journal.jsonl"
    # denied before apply, so no verified entry for this patch? journal may be empty or not contain verified for this intent
    if journal.exists():
        text = journal.read_text(encoding="utf-8")
        # should not have a verified entry for the denied attempt's fingerprint
        # the denied attempt does not create a journal intent, so either empty or only previous
        assert "verified" not in text or text.count("verified") == 0

def test_cli_high_risk_approved_via_real_approval_store():
    ws = Path(tempfile.mkdtemp(prefix="cli_high_ok_"))
    target = ws / "demo.txt"
    target.write_text("hello\n", encoding="utf-8")
    # stage A denied
    r1 = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", 'api_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n', "--workspace", str(ws)], ws)
    assert r1.returncode != 0
    assert "Failure stage: approval" in r1.stdout
    # grant real approval
    r2 = _run_cli(["approve", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", 'api_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n', "--workspace", str(ws)], ws)
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "Approval granted" in r2.stdout
    assert "bound to fingerprint" in r2.stdout
    # stage B succeeds
    r3 = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", 'api_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n', "--workspace", str(ws)], ws)
    assert r3.returncode == 0, r3.stdout + r3.stderr
    assert "Apply success: True" in r3.stdout
    assert "Verification passed: True" in r3.stdout
    assert "Terminal state: VERIFIED" in r3.stdout
    # file content is without quotes due to shell handling? check contains api_key
    assert "api_key" in _read(target)

def test_cli_approval_replay_denied():
    ws = Path(tempfile.mkdtemp(prefix="cli_replay_"))
    target = ws / "demo.txt"
    target.write_text("hello\n", encoding="utf-8")
    _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", 'api_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n', "--workspace", str(ws)], ws)
    _run_cli(["approve", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", 'api_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n', "--workspace", str(ws)], ws)
    r_ok = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", 'api_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n', "--workspace", str(ws)], ws)
    assert r_ok.returncode == 0
    # restore to allow replay attempt
    target.write_text("hello\n", encoding="utf-8")
    r_replay = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", 'api_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n', "--workspace", str(ws)], ws)
    assert r_replay.returncode != 0
    assert "Failure stage: approval" in r_replay.stdout
    assert _read(target) == "hello\n"

def test_cli_path_traversal_denied():
    ws = Path(tempfile.mkdtemp(prefix="cli_traversal_"))
    (ws / "demo.txt").write_text("hello\n", encoding="utf-8")
    # try to escape workspace via ../
    r = _run_cli(["apply", "--file", "../evil.txt", "--old-content", "hello\n", "--new-content", "hacked\n", "--workspace", str(ws)], ws)
    assert r.returncode != 0
    # should be denied at validation, not applied
    assert "Failure stage: validation" in r.stdout or "Apply success: False" in r.stdout
    # ensure no file created outside
    assert not (ws.parent / "evil.txt").exists()

def test_cli_rollback_on_verification_failure():
    ws = Path(tempfile.mkdtemp(prefix="cli_rollback_"))
    target = ws / "app.py"
    target.write_text("x = 1\n", encoding="utf-8")
    r = _run_cli(["apply", "--file", "app.py", "--old-content", "x = 1\n", "--new-content", "x = 1\n syntax error !!!\n", "--workspace", str(ws)], ws)
    assert r.returncode != 0
    assert "Apply success: True" in r.stdout  # apply occurred before verification
    assert "Verification passed: False" in r.stdout
    assert "Rollback: YES" in r.stdout
    assert "Terminal state: ROLLED_BACK" in r.stdout
    assert _read(target) == "x = 1\n"
    journal = ws / ".cli_platform" / "apply_journal.jsonl"
    assert "rolled_back" in journal.read_text(encoding="utf-8")
    assert "verified" not in journal.read_text(encoding="utf-8").split("rolled_back")[-1] or journal.read_text(encoding="utf-8").count("verified") == 0

def test_cli_no_direct_write_bypass():
    ws = Path(tempfile.mkdtemp(prefix="cli_bypass_"))
    target = ws / "demo.txt"
    target.write_text("hello\n", encoding="utf-8")
    # high without approval should not write via any direct FileApplier bypass
    r = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", 'api_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n', "--workspace", str(ws)], ws)
    assert r.returncode != 0
    # ensure file unchanged (no direct write)
    assert _read(target) == "hello\n"
