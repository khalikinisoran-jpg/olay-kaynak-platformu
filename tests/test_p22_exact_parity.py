"""P2.2 exact approval fingerprint parity — pending workflow.

Covers required tests:
1. LOW-risk task still works.
2. HIGH-risk task without approval is denied.
3. Human can approve exact HIGH-risk proposal via supported CLI (approve --pending).
4. Re-running same HIGH-risk task after approval succeeds.
5. Different proposal does NOT consume or match that approval.
6. Single-use/replay protection.
7. Approval remains bound to exact proposal fingerprint.
8. Newline/quoting behavior cannot silently cause mismatch in supported workflow.
"""
import subprocess, sys, tempfile, json, re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

def _run(args):
    cmd=[sys.executable,"agent_run.py"]+args
    return subprocess.run(cmd,cwd=str(REPO_ROOT),capture_output=True,text=True)

def _extract_fingerprint(stdout, prefix="fingerprint="):
    # try multiple patterns
    m=re.search(r"fingerprint=([a-f0-9]{12,})", stdout)
    if m:
        return m.group(1)
    m=re.search(r"fingerprint (\w+)", stdout)
    if m:
        return m.group(1)
    return None

def test_low_risk_still_works():
    ws=Path(tempfile.mkdtemp(prefix="p22_low_"))
    t=ws/"demo.txt"
    t.write_text("hello\n",encoding="utf-8")
    r=_run(["task","--goal","fix hello file","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r.returncode==0, r.stdout+r.stderr
    assert "Risk: LOW" in r.stdout
    assert "Terminal state: VERIFIED" in r.stdout
    assert t.read_text(encoding="utf-8")=="hello fixed\n"

def test_high_denied_without_approval():
    ws=Path(tempfile.mkdtemp(prefix="p22_high_denied_"))
    t=ws/"demo.txt"
    t.write_text("hello\n",encoding="utf-8")
    r=_run(["task","--goal","add api_key secret to file","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r.returncode!=0
    assert "Risk: HIGH" in r.stdout
    assert "Failure stage: approval" in r.stdout
    assert t.read_text(encoding="utf-8")=="hello\n"

def test_high_approved_via_pending_exact_parity():
    ws=Path(tempfile.mkdtemp(prefix="p22_high_pending_"))
    t=ws/"demo.txt"
    t.write_text("hello\n",encoding="utf-8")
    r1=_run(["task","--goal","add api_key secret to file","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r1.returncode!=0
    m=re.search(r"fingerprint=([a-f0-9]+)", r1.stdout)
    assert m
    worker_fp=m.group(1)
    # pending file stores exact proposal
    pending=ws/".cli_platform"/"pending_proposals.json"
    assert pending.exists(), "pending proposals should be persisted"
    data=json.loads(pending.read_text(encoding="utf-8"))
    assert len(data)==1
    assert data[0]["fingerprint"][:12]==worker_fp
    # approve via pending (no manual old/new)
    r2=_run(["approve","--pending","--workspace",str(ws)])
    assert r2.returncode==0, r2.stdout+r2.stderr
    assert "Approval granted" in r2.stdout
    assert worker_fp in r2.stdout or data[0]["fingerprint"][:12] in r2.stdout
    # re-run same task succeeds
    r3=_run(["task","--goal","add api_key secret to file","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r3.returncode==0, r3.stdout+r3.stderr
    assert "Terminal state: VERIFIED" in r3.stdout
    assert "api_key" in t.read_text(encoding="utf-8")
    # fingerprint parity: worker fp should equal approved fingerprint
    m3=re.search(r"fingerprint=([a-f0-9]+)", r3.stdout)
    assert m3
    assert m3.group(1)==worker_fp

def test_different_proposal_does_not_match_approval():
    ws=Path(tempfile.mkdtemp(prefix="p22_diff_"))
    t=ws/"demo.txt"
    t.write_text("hello\n",encoding="utf-8")
    r1=_run(["task","--goal","add api_key secret to file","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r1.returncode!=0
    r2=_run(["approve","--pending","--workspace",str(ws)])
    assert r2.returncode==0
    # change file to produce different old_content -> different fingerprint
    t.write_text("hello world\n",encoding="utf-8")
    r3=_run(["task","--goal","add api_key secret to file","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    # should be denied because approval for hello does not match hello world
    assert r3.returncode!=0
    assert "Failure stage: approval" in r3.stdout
    assert t.read_text(encoding="utf-8")=="hello world\n"

def test_single_use_replay_protection():
    ws=Path(tempfile.mkdtemp(prefix="p22_replay_"))
    t=ws/"demo.txt"
    t.write_text("hello\n",encoding="utf-8")
    r1=_run(["task","--goal","add api_key secret to file","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r1.returncode!=0
    r2=_run(["approve","--pending","--workspace",str(ws)])
    assert r2.returncode==0
    r3=_run(["task","--goal","add api_key secret to file","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r3.returncode==0
    # restore file to original to attempt replay of same fingerprint
    t.write_text("hello\n",encoding="utf-8")
    r4=_run(["task","--goal","add api_key secret to file","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r4.returncode!=0
    assert "Failure stage: approval" in r4.stdout

def test_approval_bound_to_exact_fingerprint():
    ws=Path(tempfile.mkdtemp(prefix="p22_bound_"))
    t=ws/"demo.txt"
    t.write_text("hello\n",encoding="utf-8")
    r1=_run(["task","--goal","add api_key secret to file","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r1.returncode!=0
    pending=json.loads((ws/".cli_platform"/"pending_proposals.json").read_text(encoding="utf-8"))
    fp=pending[0]["fingerprint"]
    # manually try to approve a different fingerprint (tampered new_content) should not authorize original
    # we do this by directly using approval ledger: grant for different fingerprint and then try task
    # Simpler: approve pending for original, then try a materially different goal that produces different new_content
    r2=_run(["approve","--pending","--workspace",str(ws)])
    assert r2.returncode==0
    # now modify goal to produce LOW proposal (different fingerprint, different risk) – should not require HIGH approval but should succeed via LOW path
    # Instead test that approval for HIGH does not authorize a different HIGH proposal with different content
    # Create a second file with different content that also triggers HIGH but different old/new
    t2=ws/"other.txt"
    t2.write_text("hello\n",encoding="utf-8")
    # Task without file hint will discover both, but we can run task on other.txt with same goal but different path -> fingerprint differs due to path
    r3=_run(["task","--goal","add api_key secret to file","--workspace",str(ws),"--file","other.txt","--fake-analyzer"])
    # The previous approval was for demo.txt, not other.txt, so this should be denied (different path fingerprint)
    assert r3.returncode!=0
    assert "Failure stage: approval" in r3.stdout

def test_newline_quoting_exact_parity():
    # File contains exactly "hello" without newline – pending must handle newline correctly
    ws=Path(tempfile.mkdtemp(prefix="p22_newline_"))
    t=ws/"demo.txt"
    t.write_text("hello",encoding="utf-8")  # no newline, as per mission demo
    r1=_run(["task","--goal","replace the file content with api_key = sk-test-key-aaaaaaaaaaaaaaaa","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r1.returncode!=0
    assert "Risk: HIGH" in r1.stdout
    pending=json.loads((ws/".cli_platform"/"pending_proposals.json").read_text(encoding="utf-8"))
    # old_content should be exactly "hello" (no newline), new_content with newline+api_key
    assert pending[0]["old_content"]=="hello"
    assert pending[0]["new_content"]=="hello\napi_key = \"sk-test-key-aaaaaaaaaaaaaaaa\"\n"
    # approve via pending should succeed without manual newline quoting
    r2=_run(["approve","--pending","--workspace",str(ws)])
    assert r2.returncode==0
    r3=_run(["task","--goal","replace the file content with api_key = sk-test-key-aaaaaaaaaaaaaaaa","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r3.returncode==0
    assert "VERIFIED" in r3.stdout
    assert t.read_text(encoding="utf-8")=="hello\napi_key = \"sk-test-key-aaaaaaaaaaaaaaaa\"\n"
    # Also test that manual approve with wrong newline (hello\n) would have failed, proving pending avoids quoting pitfall
    ws2=Path(tempfile.mkdtemp(prefix="p22_newline_manual_"))
    t2=ws2/"demo.txt"
    t2.write_text("hello",encoding="utf-8")
    r4=_run(["task","--goal","add api_key secret","--workspace",str(ws2),"--file","demo.txt","--fake-analyzer"])
    assert r4.returncode!=0
    # manual approve with wrong old_content "hello\n" should produce different fingerprint and not authorize
    r5=_run(["approve","--file","demo.txt","--old-content","hello\n","--new-content","hello\napi_key = \"sk-test-key-aaaaaaaaaaaaaaaa\"\n","--workspace",str(ws2)])
    assert r5.returncode==0  # grant succeeds but for wrong fingerprint
    r6=_run(["task","--goal","add api_key secret","--workspace",str(ws2),"--file","demo.txt","--fake-analyzer"])
    # should still be denied because fingerprint mismatch (manual wrong old)
    assert r6.returncode!=0
    assert "Failure stage: approval" in r6.stdout
    # now correct via pending should succeed
    r7=_run(["approve","--pending","--workspace",str(ws2)])
    assert r7.returncode==0
    r8=_run(["task","--goal","add api_key secret","--workspace",str(ws2),"--file","demo.txt","--fake-analyzer"])
    assert r8.returncode==0

def test_pending_fingerprint_filter():
    ws=Path(tempfile.mkdtemp(prefix="p22_fp_filter_"))
    t=ws/"demo.txt"
    t.write_text("hello\n",encoding="utf-8")
    r1=_run(["task","--goal","add api_key secret","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r1.returncode!=0
    pending=json.loads((ws/".cli_platform"/"pending_proposals.json").read_text(encoding="utf-8"))
    full_fp=pending[0]["fingerprint"]
    # approve with fingerprint prefix
    r2=_run(["approve","--pending","--fingerprint",full_fp[:8],"--workspace",str(ws)])
    assert r2.returncode==0
    assert "Granted 1" in r2.stdout
    r3=_run(["task","--goal","add api_key secret","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r3.returncode==0

def test_manual_approve_still_works_subprocess_list():
    # Backward compat: manual old/new via subprocess list (no shell quoting) should still work
    ws=Path(tempfile.mkdtemp(prefix="p22_manual_"))
    t=ws/"demo.txt"
    t.write_text("hello\n",encoding="utf-8")
    r1=_run(["task","--goal","add api_key secret","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r1.returncode!=0
    r2=_run(["approve","--file","demo.txt","--old-content","hello\n","--new-content","hello\napi_key = \"sk-test-key-aaaaaaaaaaaaaaaa\"\n","--workspace",str(ws)])
    assert r2.returncode==0
    r3=_run(["task","--goal","add api_key secret","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r3.returncode==0
