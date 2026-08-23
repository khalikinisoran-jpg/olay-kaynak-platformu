"""MISSION N.94 — CLI observability regression.

Proves:
1. current operation output is filtered/correlated correctly
2. old journal entries do not appear in current operation lifecycle
3. denied-before-apply does not fabricate a lifecycle
4. historical inspection, if implemented, is read-only
"""
import subprocess
import sys
import tempfile
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

def _run_cli(args):
    cmd = [sys.executable, "agent_run.py"] + args
    return subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)

def _intent_from_output(stdout):
    m = re.search(r"Intent ID: ([a-f0-9]{8})", stdout)
    if m:
        return m.group(1)
    # denied case has no intent
    if "(none — no apply intent created)" in stdout:
        return None
    return None

def test_current_operation_lifecycle_filtered():
    ws = Path(tempfile.mkdtemp(prefix="cli_obs_filter_"))
    target = ws / "demo.txt"
    target.write_text("hello\n", encoding="utf-8")
    # first op
    r1 = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", "hello v1\n", "--workspace", str(ws)])
    assert r1.returncode == 0, r1.stdout + r1.stderr
    intent1 = _intent_from_output(r1.stdout)
    assert intent1 is not None
    assert "CURRENT OPERATION" in r1.stdout
    assert "CURRENT OPERATION LIFECYCLE" in r1.stdout
    # lifecycle should contain only intent1
    lifecycle1 = r1.stdout.split("CURRENT OPERATION LIFECYCLE")[-1]
    assert intent1 in lifecycle1
    # second op in same workspace
    target.write_text("hello v1\n", encoding="utf-8")
    r2 = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello v1\n", "--new-content", "hello v2\n", "--workspace", str(ws)])
    assert r2.returncode == 0, r2.stdout + r2.stderr
    intent2 = _intent_from_output(r2.stdout)
    assert intent2 is not None
    assert intent1 != intent2
    lifecycle2 = r2.stdout.split("CURRENT OPERATION LIFECYCLE")[-1]
    assert intent2 in lifecycle2
    assert intent1 not in lifecycle2, "old journal entry must not appear in current lifecycle"
    # also ensure full journal file has both intents, but output did not mix
    journal = ws / ".cli_platform" / "apply_journal.jsonl"
    assert journal.exists()
    text = journal.read_text(encoding="utf-8")
    assert intent1 in text
    assert intent2 in text

def test_denied_before_apply_no_fabricated_lifecycle():
    ws = Path(tempfile.mkdtemp(prefix="cli_obs_denied_"))
    target = ws / "demo.txt"
    target.write_text("hello\n", encoding="utf-8")
    high_content = 'api_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n'
    r = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", high_content, "--workspace", str(ws)])
    assert r.returncode != 0
    assert "Risk: HIGH" in r.stdout
    assert "Approval required: True" in r.stdout
    assert "Failure stage: approval" in r.stdout
    assert "No apply journal created." in r.stdout
    assert "Operation denied at: approval" in r.stdout
    assert "Terminal state: DENIED" in r.stdout
    # must not fabricate verified
    assert "Terminal state: VERIFIED" not in r.stdout
    lifecycle = r.stdout.split("CURRENT OPERATION LIFECYCLE")[-1]
    # denied lifecycle must not contain verified/rolled_back as if it succeeded
    # It should explicitly say no journal and denied
    assert "intent" not in lifecycle or "No apply journal" in lifecycle
    # journal file should not contain verified for this denied attempt
    journal = ws / ".cli_platform" / "apply_journal.jsonl"
    if journal.exists():
        txt = journal.read_text(encoding="utf-8")
        # denied before apply creates no intent, so no verified for this fingerprint in this fresh ws
        assert "verified" not in txt

def test_denied_after_mixed_history_still_isolated():
    ws = Path(tempfile.mkdtemp(prefix="cli_obs_mixed_denied_"))
    target = ws / "demo.txt"
    target.write_text("hello\n", encoding="utf-8")
    r_low = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", "hello fixed\n", "--workspace", str(ws)])
    assert r_low.returncode == 0
    intent_low = _intent_from_output(r_low.stdout)
    high_content = 'api_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n'
    # file now hello fixed
    r_denied = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello fixed\n", "--new-content", high_content, "--workspace", str(ws)])
    assert r_denied.returncode != 0
    lifecycle = r_denied.stdout.split("CURRENT OPERATION LIFECYCLE")[-1]
    assert intent_low not in lifecycle
    assert "No apply journal created." in lifecycle
    assert "Operation denied at: approval" in lifecycle

def test_history_is_read_only():
    ws = Path(tempfile.mkdtemp(prefix="cli_obs_history_"))
    target = ws / "demo.txt"
    target.write_text("hello\n", encoding="utf-8")
    r1 = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", "hello v1\n", "--workspace", str(ws)])
    assert r1.returncode == 0
    journal = ws / ".cli_platform" / "apply_journal.jsonl"
    assert journal.exists()
    before = journal.read_bytes()
    before_stat = journal.stat()
    r_hist = _run_cli(["history", "--workspace", str(ws)])
    assert r_hist.returncode == 0
    assert "APPLY HISTORY" in r_hist.stdout
    assert "READ ONLY" in r_hist.stdout
    after = journal.read_bytes()
    assert before == after, "history must not mutate journal"
    assert journal.stat().st_size == before_stat.st_size
    # history shows intent correlation
    intent1 = _intent_from_output(r1.stdout)
    assert intent1 in r_hist.stdout
    assert "Lifecycle:" in r_hist.stdout
    assert "Terminal:" in r_hist.stdout
    # status alias should also work and be read-only
    r_status = _run_cli(["status", "--workspace", str(ws)])
    assert r_status.returncode == 0
    assert "APPLY HISTORY" in r_status.stdout
    assert journal.read_bytes() == before

def test_approval_visibility_states():
    ws = Path(tempfile.mkdtemp(prefix="cli_obs_approval_"))
    target = ws / "demo.txt"
    target.write_text("hello\n", encoding="utf-8")
    # LOW not required
    r_low = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", "hello fixed\n", "--workspace", str(ws)])
    assert "Approval state: not required" in r_low.stdout
    assert "Approval ID: (not required)" in r_low.stdout
    # HIGH denied
    ws2 = Path(tempfile.mkdtemp(prefix="cli_obs_approval2_"))
    (ws2 / "demo.txt").write_text("hello\n", encoding="utf-8")
    high_content = 'api_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n'
    r_denied = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", high_content, "--workspace", str(ws2)])
    assert "Approval state: required but missing / denied" in r_denied.stdout
    assert "Approval ID: (none)" in r_denied.stdout
    # HIGH granted
    r_approve = _run_cli(["approve", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", high_content, "--workspace", str(ws2)])
    assert r_approve.returncode == 0
    m = re.search(r"Approval granted: ([a-f0-9]{8})", r_approve.stdout)
    assert m
    approve_short = m.group(1)
    r_ok = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", high_content, "--workspace", str(ws2)])
    assert r_ok.returncode == 0
    assert "Approval state: granted and accepted" in r_ok.stdout
    assert approve_short in r_ok.stdout
    # replay consumed
    (ws2 / "demo.txt").write_text("hello\n", encoding="utf-8")
    r_replay = _run_cli(["apply", "--file", "demo.txt", "--old-content", "hello\n", "--new-content", high_content, "--workspace", str(ws2)])
    assert r_replay.returncode != 0
    assert "already consumed" in r_replay.stdout
    assert "single-use" in r_replay.stdout
