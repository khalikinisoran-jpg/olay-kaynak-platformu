import subprocess, sys, tempfile, pathlib
from pathlib import Path

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]

def _run(args):
    cmd=[sys.executable,"agent_run.py"]+args
    return subprocess.run(cmd,cwd=str(REPO_ROOT),capture_output=True,text=True)

def test_cli_task_low_risk_success():
    ws=Path(tempfile.mkdtemp(prefix="cli_task_low_"))
    t=ws/"demo.txt"
    t.write_text("hello\n",encoding="utf-8")
    r=_run(["task","--goal","fix hello file","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r.returncode==0, r.stdout+r.stderr
    assert "WORKER RESULT" in r.stdout
    assert "Success: True" in r.stdout
    assert "Risk: LOW" in r.stdout
    assert "Pipeline success: True" in r.stdout
    assert "Terminal state: VERIFIED" in r.stdout
    assert t.read_text(encoding="utf-8")=="hello fixed\n"

def test_cli_task_high_risk_denied_without_approval():
    ws=Path(tempfile.mkdtemp(prefix="cli_task_high_denied_"))
    t=ws/"demo.txt"
    t.write_text("hello\n",encoding="utf-8")
    r=_run(["task","--goal","add api_key secret to file","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r.returncode!=0
    assert "Risk: HIGH" in r.stdout
    assert "Approval required: True" in r.stdout
    assert "Failure stage: approval" in r.stdout
    assert "Terminal state: DENIED" in r.stdout
    assert t.read_text(encoding="utf-8")=="hello\n"

def test_cli_task_high_risk_approved():
    ws=Path(tempfile.mkdtemp(prefix="cli_task_high_ok_"))
    t=ws/"demo.txt"
    t.write_text("hello\n",encoding="utf-8")
    r1=_run(["task","--goal","add api_key secret to file","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r1.returncode!=0
    # approve same patch (old hello, new hello\napi_key ...)
    high_new='hello\napi_key = "sk-test-key-aaaaaaaaaaaaaaaa"\n'
    r2=_run(["approve","--file","demo.txt","--old-content","hello\n","--new-content",high_new,"--workspace",str(ws)])
    assert r2.returncode==0, r2.stdout+r2.stderr
    assert "Approval granted" in r2.stdout
    r3=_run(["task","--goal","add api_key secret to file","--workspace",str(ws),"--file","demo.txt","--fake-analyzer"])
    assert r3.returncode==0, r3.stdout+r3.stderr
    assert "Terminal state: VERIFIED" in r3.stdout
    assert "api_key" in t.read_text(encoding="utf-8")

def test_cli_task_scope_denied():
    ws=Path(tempfile.mkdtemp(prefix="cli_task_scope_"))
    t=ws/"demo.txt"
    t.write_text("hello\n",encoding="utf-8")
    outside=Path(tempfile.mkdtemp(prefix="outside_"))/"evil.txt"
    outside.write_text("hello\n",encoding="utf-8")
    r=_run(["task","--goal","fix evil file","--workspace",str(ws),"--file",str(outside),"--fake-analyzer"])
    assert r.returncode!=0
    assert "No patches proposed" in r.stdout or "outside the allowed scope" in r.stdout

def test_cli_task_rollback_on_verification_failure():
    ws=Path(tempfile.mkdtemp(prefix="cli_task_rollback_"))
    t=ws/"app.py"
    t.write_text("x = 1\n",encoding="utf-8")
    r=_run(["task","--goal","introduce syntax error for rollback","--workspace",str(ws),"--file","app.py","--fake-analyzer"])
    assert r.returncode!=0
    assert "Verification passed: False" in r.stdout
    assert "Rollback: YES" in r.stdout
    assert "Terminal state: ROLLED_BACK" in r.stdout
    assert t.read_text(encoding="utf-8")=="x = 1\n"

def test_cli_task_dry_run():
    ws=Path(tempfile.mkdtemp(prefix="cli_task_dry_"))
    t=ws/"demo.txt"
    t.write_text("hello\n",encoding="utf-8")
    r=_run(["task","--goal","fix hello file","--workspace",str(ws),"--file","demo.txt","--fake-analyzer","--dry-run"])
    assert r.returncode==0
    assert "Dry-run" in r.stdout
    assert t.read_text(encoding="utf-8")=="hello\n"
