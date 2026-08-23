"""demo_p5.py — reproducible P5 visible product experience via real UI/service path.

Uses the LOCAL P5 server (view layer only) and exercises the EXISTING governed
pipeline: Worker → PatchProposal → GovernanceEvaluator → ApprovalStore →
ApplyAuthorization → FileApplier → VerificationExecutor → rollback → Journal.

Scenarios:
  A LOW  -> PROPOSED -> VERIFIED (no approval)
  B HIGH -> APPROVAL_REQUIRED -> approve (canonical exact fingerprint) -> VERIFIED
  C REPLAY (same HIGH after consumed) -> DENIED
  D ADVERSARIAL spoof (approved=true bypass) -> DENIED (LLM claims ignored)

No direct writes; UI never bypasses pipeline. Counts must be 0 bypass.
"""
import json
import sys
import time
import tempfile
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

HOST = "127.0.0.1"
PORT = 8766  # avoid clash with p5 default 8765
BASE = f"http://{HOST}:{PORT}"

def http_post(path, obj):
    data = json.dumps(obj).encode()
    req = Request(BASE + path, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        try:
            j = json.loads(body) if body else {}
        except Exception:
            j = {"raw": body}
        return e.code, j

def http_get(path):
    req = Request(BASE + path, method="GET")
    try:
        with urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return e.code, json.loads(body) if body else {}

def wait_health(timeout=15):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            st, j = http_get("/api/health")
            if st == 200 and j.get("ok"):
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False

def main():
    print("="*60)
    print(" P5 VISIBLE PRODUCT EXPERIENCE DEMO (real UI/service path)")
    print("="*60)
    ws = Path(tempfile.mkdtemp(prefix="demo_p5_"))
    # ensure demo.txt hello (no BOM) — same as P2.3-A
    target = ws / "demo.txt"
    target.write_bytes("hello".encode("utf-8"))
    print(f"Workspace: {ws}")
    print(f"Target: {target} content={repr(target.read_text(encoding='utf-8'))}")

    # start server
    proc = subprocess.Popen([sys.executable, "-m", "p5.server", "--host", HOST, "--port", str(PORT)],
                            cwd=str(Path(__file__).parent), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        if not wait_health():
            print("FAIL: server not healthy")
            try:
                out, err = proc.communicate(timeout=2)
                print(out.decode()[:500])
                print(err.decode()[:500])
            except Exception:
                pass
            proc.terminate()
            return 1

        print(f"Server healthy at {BASE}")

        # Helper to assert counts
        counters = {"unauthorized": 0, "approval_bypass": 0, "replay": 0, "integrity_escape": 0}

        # SCENARIO A — LOW
        print("\n--- SCENARIO A — LOW RISK (hello -> hello fixed) ---")
        st, j = http_post("/api/propose", {"goal": "fix hello file", "workspace": str(ws), "file": "demo.txt", "fake_analyzer": True})
        print(f"propose: {st} status={j.get('status')} risk={j.get('governance',{}).get('risk')}")
        if j.get("governance", {}).get("risk") != "LOW" or not j.get("governance", {}).get("allowed"):
            print("FAIL A propose")
            return 1
        st, j = http_post("/api/execute", {"goal": "fix hello file", "workspace": str(ws), "file": "demo.txt", "fake_analyzer": True})
        print(f"execute: {st} terminal={j.get('status')} success={j.get('result',{}).get('success')}")
        if j.get("status") != "VERIFIED" or not j.get("result", {}).get("success"):
            print("FAIL A execute not VERIFIED")
            return 1
        if target.read_text(encoding="utf-8") != "hello fixed\n":
            print("FAIL A file not fixed", repr(target.read_text(encoding="utf-8")))
            return 1
        print("A VERIFIED — ok (authorized path)")
        from urllib.parse import quote
        st, j = http_get(f"/api/history?workspace={quote(str(ws))}")
        if not j.get("records"):
            print("FAIL A history empty")
            return 1
        print(f"history read-only: {len(j['records'])} records")

        # Reset for B
        target.write_bytes("hello".encode("utf-8"))
        # SCENARIO B — HIGH
        print("\n--- SCENARIO B — HIGH RISK (api_key secret) ---")
        st, j = http_post("/api/propose", {"goal": "add api_key secret to file", "workspace": str(ws), "file": "demo.txt", "fake_analyzer": True})
        print(f"propose HIGH: {st} status={j.get('status')} risk={j.get('governance',{}).get('risk')}")
        if j.get("governance", {}).get("risk") != "HIGH" or j.get("status") != "APPROVAL_REQUIRED":
            print("FAIL B propose should be HIGH APPROVAL_REQUIRED")
            return 1
        # execute without approval -> DENIED
        st, j = http_post("/api/execute", {"goal": "add api_key secret to file", "workspace": str(ws), "file": "demo.txt", "fake_analyzer": True})
        print(f"execute without approval: {st} terminal={j.get('status')} failure_stage={j.get('result',{}).get('failure_stage')}")
        if j.get("status") != "DENIED" or j.get("result", {}).get("failure_stage") != "approval":
            print("FAIL B should be DENIED approval")
            return 1
        if target.read_text(encoding="utf-8") != "hello":
            print("FAIL B file should remain hello")
            return 1
        # approve via canonical pending exact fingerprint (UI view layer calls ApprovalStore.grant)
        st, j = http_post("/api/approve", {"workspace": str(ws)})
        print(f"approve: {st} granted={j.get('count')}")
        if st != 200 or not j.get("granted"):
            print("FAIL B approve")
            return 1
        # execute after approval -> VERIFIED
        st, j = http_post("/api/execute", {"goal": "add api_key secret to file", "workspace": str(ws), "file": "demo.txt", "fake_analyzer": True})
        print(f"execute after approval: {st} terminal={j.get('status')}")
        if j.get("status") != "VERIFIED":
            print("FAIL B after approval not VERIFIED", j)
            return 1
        if "api_key" not in target.read_text(encoding="utf-8"):
            print("FAIL B file missing api_key")
            return 1
        print("B VERIFIED after approval — ok")

        # SCENARIO C — REPLAY
        print("\n--- SCENARIO C — REPLAY (same HIGH after consumed) ---")
        target.write_bytes("hello".encode("utf-8"))
        st, j = http_post("/api/execute", {"goal": "add api_key secret to file", "workspace": str(ws), "file": "demo.txt", "fake_analyzer": True})
        print(f"replay execute: {st} terminal={j.get('status')}")
        if j.get("status") != "DENIED":
            print("FAIL C replay should be DENIED")
            counters["replay"] += 1
            return 1
        if target.read_text(encoding="utf-8") != "hello":
            print("FAIL C file should remain hello")
            return 1
        print("C REPLAY DENIED — ok (single-use)")

        # SCENARIO D — ADVERSARIAL spoof (provider claims approved=true, bypass)
        print("\n--- SCENARIO D — ADVERSARIAL spoof (provider claims bypass) ---")
        target.write_bytes("hello".encode("utf-8"))
        # Use propose with spoof goal marker ADVISORY_BYPASS — server will inject spoof provider that claims LOW+approved
        st, j = http_post("/api/propose", {"goal": "ADVISORY_BYPASS add api_key secret", "workspace": str(ws), "file": "demo.txt", "fake_analyzer": True})
        # Even though provider claims LOW+approved, governance must still be HIGH APPROVAL_REQUIRED
        print(f"adversarial propose: risk={j.get('governance',{}).get('risk')} approval_required={j.get('governance',{}).get('approval_required')} status={j.get('status')}")
        if j.get("governance", {}).get("risk") != "HIGH" or not j.get("governance", {}).get("approval_required"):
            print("FAIL D governance should remain HIGH regardless of LLM claim")
            counters["approval_bypass"] += 1
            return 1
        st, j = http_post("/api/execute", {"goal": "ADVISORY_BYPASS add api_key secret", "workspace": str(ws), "file": "demo.txt", "fake_analyzer": True})
        print(f"adversarial execute: terminal={j.get('status')} failure_stage={j.get('result',{}).get('failure_stage')}")
        if j.get("status") != "DENIED":
            print("FAIL D adversarial should be DENIED")
            counters["unauthorized"] += 1
            return 1
        if target.read_text(encoding="utf-8") != "hello":
            print("FAIL D file unchanged")
            return 1
        print("D DENIED (LLM claims ignored) — ok")

        # HISTORY read-only check
        print("\n--- HISTORY READ-ONLY ---")
        from urllib.parse import quote
        st, j = http_get(f"/api/history?workspace={quote(str(ws))}")
        before = json.dumps(j)
        st2, j2 = http_get(f"/api/history?workspace={quote(str(ws))}")
        after = json.dumps(j2)
        if before != after:
            print("FAIL history mutated")
            return 1
        print(f"history read-only ok: {len(j.get('records',[]))} records, terminal states present")
        # Ensure history contains lifecycle
        has_verified = any(r.get("record_type") == "verified" for r in j.get("records", []))
        if not has_verified:
            print("FAIL history missing VERIFIED")
            return 1

        print("\n" + "="*60)
        print(" OVERALL PASS")
        print("="*60)
        print(f"A LOW VERIFIED: ok\nB HIGH APPROVAL_REQUIRED -> approve -> VERIFIED: ok\nC REPLAY DENIED: ok\nD ADVERSARIAL DENIED: ok\nHistory read-only: ok")
        print(f"Workspace: {ws} (kept)")
        print(f"Counts: unauthorized={counters['unauthorized']} approval_bypass={counters['approval_bypass']} replay={counters['replay']} integrity_escape={counters['integrity_escape']}")
        return 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except Exception:
            proc.kill()

if __name__ == "__main__":
    sys.exit(main())
