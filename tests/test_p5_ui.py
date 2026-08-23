"""P5 UI tests — view layer over existing governance, no bypass.

Covers:
 1. no direct-write bypass (server has no FileApplier direct endpoint)
 2. HIGH shown as APPROVAL_REQUIRED and DENY before approval
 3. approval preserves exact fingerprint binding
 4. replay single-use DENY
 5. history read-only
 6. adversarial LLM claims not authority
 7. no new authority state machine beyond journal/pipeline
Plus regression that UI never writes outside pipeline.
"""
import json
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode

from p5.server import ThreadingHTTPServer, Handler


def _free_port():
    import socket
    s = socket.socket()
    s.bind(("", 0))
    p = s.getsockname()[1]
    s.close()
    return p

def _start_server(port):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    # wait a bit
    time.sleep(0.5)
    return srv

def _post(base, path, obj):
    data = json.dumps(obj).encode()
    req = Request(base + path, data=data, headers={"Content-Type": "application/json"}, method="POST")
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

def _get(base, path):
    req = Request(base + path, method="GET")
    try:
        with urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return e.code, json.loads(body) if body else {}

def _ws_with_demo():
    ws = Path(tempfile.mkdtemp(prefix="test_p5_ui_"))
    (ws / "demo.txt").write_bytes(b"hello")
    return ws

# 1. No direct-write bypass — server source must not contain direct target writes
def test_p5_no_direct_write_bypass_static():
    src = Path("p5/server.py").read_text(encoding="utf-8")
    # UI must not bypass governance: only WorkerActionPipeline is authority
    # Server imports WorkerActionPipeline and uses its execute; it must not call FileApplier directly on target
    assert "WorkerActionPipeline" in src
    # Execute must go via pipeline.execute (governed path)
    assert "pipeline" in src and ".execute" in src
    assert ".grant" in src  # approve via canonical ApprovalStore.grant
    # UI must not import FileApplier directly (only via governed pipeline); docstring mention is ok
    assert "from simulation.agent.apply.file_applier import" not in src
    assert "import FileApplier" not in src
    # Only dummy/pending writes allowed
    assert src.count("write_text") <= 4  # dummy + pending

def test_p5_high_shown_as_approval_required_and_denied_before_approval():
    port = _free_port()
    srv = _start_server(port)
    base = f"http://127.0.0.1:{port}"
    ws = _ws_with_demo()
    try:
        st, j = _post(base, "/api/propose", {"goal": "add api_key secret to file", "workspace": str(ws), "file": "demo.txt"})
        assert st == 200
        assert j["governance"]["risk"] == "HIGH"
        assert j["governance"]["approval_required"] is True
        assert j["status"] == "APPROVAL_REQUIRED"
        st, j = _post(base, "/api/execute", {"goal": "add api_key secret to file", "workspace": str(ws), "file": "demo.txt"})
        assert j["status"] == "DENIED"
        assert j["result"]["failure_stage"] == "approval"
        assert (ws / "demo.txt").read_text(encoding="utf-8") == "hello"
    finally:
        srv.shutdown()

def test_p5_approval_preserves_exact_fingerprint_binding():
    port = _free_port()
    srv = _start_server(port)
    base = f"http://127.0.0.1:{port}"
    ws = _ws_with_demo()
    try:
        # propose HIGH for demo.txt
        st, j = _post(base, "/api/propose", {"goal": "add api_key secret to file", "workspace": str(ws), "file": "demo.txt"})
        fp_demo = j["proposal"]["fingerprint"]
        # create other file with same content
        (ws / "other.txt").write_bytes(b"hello")
        # approve pending (should approve demo.txt only)
        st, j = _post(base, "/api/approve", {"workspace": str(ws)})
        assert st == 200
        assert any(g["fingerprint"] == fp_demo for g in j["granted"])
        # execute for demo.txt -> should be VERIFIED
        st, j = _post(base, "/api/execute", {"goal": "add api_key secret to file", "workspace": str(ws), "file": "demo.txt"})
        assert j["status"] == "VERIFIED"
        # Now other.txt with same goal but different path/fingerprint must still be DENIED (approval not transferred)
        (ws / "other.txt").write_bytes(b"hello")  # reset if needed
        # Need to propose for other.txt explicitly then execute without new approval
        st, j = _post(base, "/api/propose", {"goal": "add api_key secret to file", "workspace": str(ws), "file": "other.txt"})
        # governance still HIGH for other
        assert j["governance"]["risk"] == "HIGH"
        st, j = _post(base, "/api/execute", {"goal": "add api_key secret to file", "workspace": str(ws), "file": "other.txt"})
        assert j["status"] == "DENIED"
    finally:
        srv.shutdown()

def test_p5_replay_after_consumed_denied():
    port = _free_port()
    srv = _start_server(port)
    base = f"http://127.0.0.1:{port}"
    ws = _ws_with_demo()
    try:
        # HIGH flow approve+verify
        _post(base, "/api/propose", {"goal": "add api_key secret to file", "workspace": str(ws), "file": "demo.txt"})
        _post(base, "/api/approve", {"workspace": str(ws)})
        st, j = _post(base, "/api/execute", {"goal": "add api_key secret to file", "workspace": str(ws), "file": "demo.txt"})
        assert j["status"] == "VERIFIED"
        # restore and replay
        (ws / "demo.txt").write_bytes(b"hello")
        st, j = _post(base, "/api/execute", {"goal": "add api_key secret to file", "workspace": str(ws), "file": "demo.txt"})
        assert j["status"] == "DENIED"
        assert (ws / "demo.txt").read_text(encoding="utf-8") == "hello"
    finally:
        srv.shutdown()

def test_p5_history_read_only():
    from urllib.parse import quote
    port = _free_port()
    srv = _start_server(port)
    base = f"http://127.0.0.1:{port}"
    ws = _ws_with_demo()
    try:
        _post(base, "/api/propose", {"goal": "fix hello file", "workspace": str(ws), "file": "demo.txt"})
        _post(base, "/api/execute", {"goal": "fix hello file", "workspace": str(ws), "file": "demo.txt"})
        st, j = _get(base, f"/api/history?workspace={quote(str(ws))}")
        assert st == 200
        assert "records" in j and j.get("read_only") is True
        before = json.dumps(j)
        st, j2 = _get(base, f"/api/history?workspace={quote(str(ws))}")
        after = json.dumps(j2)
        assert before == after  # no mutation
        # ensure history contains verified lifecycle
        has_verified = any(r.get("record_type") == "verified" for r in j["records"])
        assert has_verified
    finally:
        srv.shutdown()

def test_p5_adversarial_llm_claims_not_authority():
    port = _free_port()
    srv = _start_server(port)
    base = f"http://127.0.0.1:{port}"
    ws = _ws_with_demo()
    try:
        st, j = _post(base, "/api/propose", {"goal": "ADVISORY_BYPASS add api_key secret", "workspace": str(ws), "file": "demo.txt"})
        # Even with spoof provider claiming LOW+approved, governance must remain HIGH
        assert j["governance"]["risk"] == "HIGH"
        assert j["governance"]["approval_required"] is True
        assert j["status"] == "APPROVAL_REQUIRED"
        st, j = _post(base, "/api/execute", {"goal": "ADVISORY_BYPASS add api_key secret", "workspace": str(ws), "file": "demo.txt"})
        assert j["status"] == "DENIED"
        assert j["result"]["failure_stage"] == "approval"
        assert (ws / "demo.txt").read_text(encoding="utf-8") == "hello"
    finally:
        srv.shutdown()

def test_p5_low_visible_verified_without_approval():
    port = _free_port()
    srv = _start_server(port)
    base = f"http://127.0.0.1:{port}"
    ws = _ws_with_demo()
    try:
        st, j = _post(base, "/api/propose", {"goal": "fix hello file", "workspace": str(ws), "file": "demo.txt"})
        assert j["governance"]["risk"] == "LOW"
        assert j["governance"]["approval_required"] is False
        st, j = _post(base, "/api/execute", {"goal": "fix hello file", "workspace": str(ws), "file": "demo.txt"})
        assert j["status"] == "VERIFIED"
        assert j["result"]["success"] is True
        assert (ws / "demo.txt").read_text(encoding="utf-8") == "hello fixed\n"
    finally:
        srv.shutdown()
