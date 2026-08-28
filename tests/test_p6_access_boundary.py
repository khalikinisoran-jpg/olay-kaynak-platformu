"""P6 access boundary — workspace confinement + local token + governance still authority."""
import json
import tempfile
import threading
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from p5.server import ThreadingHTTPServer, Handler
from p5.config import load_config

def _free_port():
    import socket
    s = socket.socket(); s.bind(("", 0)); p = s.getsockname()[1]; s.close(); return p

def _start_with_root(port, root, token=None):
    cfg = load_config(cli_host="127.0.0.1", cli_port=port, cli_workspace_root=str(root), cli_token=token)
    import p5.server as srv
    srv.CONFIG = cfg
    Handler.config = cfg
    server = ThreadingHTTPServer((cfg.host, cfg.port), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)
    return server, cfg

def _post(base, path, body, token=None):
    hdrs = {"Content-Type": "application/json"}
    if token:
        hdrs["X-P5-Token"] = token
    data = json.dumps(body).encode()
    req = Request(base + path, data=data, headers=hdrs, method="POST")
    try:
        with urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except HTTPError as e:
        return e.code, json.loads(e.read().decode()) if e.read else {}

def _get(base, path):
    req = Request(base + path, method="GET")
    try:
        with urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except HTTPError as e:
        return e.code, {}

def test_workspace_outside_root_denied():
    root = Path(tempfile.mkdtemp(prefix="p6_root_"))
    port = _free_port()
    srv, cfg = _start_with_root(port, root)
    base = f"http://127.0.0.1:{port}"
    try:
        outside = "/etc" if Path("/etc").exists() else str(Path(tempfile.gettempdir()) / "definitely_outside_p6")
        # Ensure outside is not within root
        if Path(outside).resolve().is_relative_to(root.resolve()):
            outside = str(Path(tempfile.mkdtemp(prefix="outside_")))
        status, j = _post(base, "/api/propose", {"goal": "fix hello file", "workspace": outside, "file": "demo.txt"})
        assert status == 400
        assert "outside allowed root" in j.get("error", "")
        # Ensure no dir created outside root
        assert not (Path(outside) / ".p5_platform").exists() or Path(outside) == root
    finally:
        srv.shutdown()

def test_traversal_cannot_escape_root():
    root = Path(tempfile.mkdtemp(prefix="p6_traversal_root_"))
    port = _free_port()
    srv, cfg = _start_with_root(port, root)
    base = f"http://127.0.0.1:{port}"
    try:
        traversal = str(root / ".." / "evil_traversal_p6")
        status, j = _post(base, "/api/propose", {"goal": "fix hello file", "workspace": traversal, "file": "demo.txt"})
        assert status == 400
    finally:
        srv.shutdown()

def test_token_missing_and_invalid_403():
    root = Path(tempfile.mkdtemp(prefix="p6_token_root_"))
    port = _free_port()
    token = "valid-local-token-12345678"
    srv, cfg = _start_with_root(port, root, token=token)
    base = f"http://127.0.0.1:{port}"
    ws = root / "ws1"
    ws.mkdir()
    (ws / "demo.txt").write_bytes(b"hello")
    try:
        # No token -> 403 for approve (state-changing)
        status, j = _post(base, "/api/approve", {"workspace": str(ws)})
        assert status == 403
        # Wrong token -> 403
        status, j = _post(base, "/api/approve", {"workspace": str(ws)}, token="wrong-token-xyz")
        assert status == 403
        # Correct token -> not 403 (may be 404 no pending, but not 403)
        status, j = _post(base, "/api/approve", {"workspace": str(ws)}, token=token)
        assert status != 403
    finally:
        srv.shutdown()

def test_token_does_not_bypass_governance():
    root = Path(tempfile.mkdtemp(prefix="p6_token gov_"))
    port = _free_port()
    token = "valid-token-12345678901"
    srv, cfg = _start_with_root(port, root, token=token)
    base = f"http://127.0.0.1:{port}"
    ws = root / "ws2"
    ws.mkdir()
    (ws / "demo.txt").write_bytes(b"hello")
    try:
        # Propose HIGH with valid token, but without approval -> execute must still DENY
        status, j = _post(base, "/api/propose", {"goal": "add api_key secret to file", "workspace": str(ws), "file": "demo.txt"}, token=token)
        assert j["governance"]["risk"] == "HIGH"
        status, j = _post(base, "/api/execute", {"goal": "add api_key secret to file", "workspace": str(ws), "file": "demo.txt"}, token=token)
        assert j["status"] == "DENIED"
        assert j["result"]["failure_stage"] == "approval"
        # Approve then execute with token -> VERIFIED
        status, j = _post(base, "/api/approve", {"workspace": str(ws)}, token=token)
        assert status == 200
        status, j = _post(base, "/api/execute", {"goal": "add api_key secret to file", "workspace": str(ws), "file": "demo.txt"}, token=token)
        assert j["status"] == "VERIFIED"
        # Replay must still DENY despite valid token
        (ws / "demo.txt").write_bytes(b"hello")
        status, j = _post(base, "/api/execute", {"goal": "add api_key secret to file", "workspace": str(ws), "file": "demo.txt"}, token=token)
        assert j["status"] == "DENIED"
    finally:
        srv.shutdown()

def test_no_token_single_operator_still_works():
    # Without token, localhost single-operator should work
    root = Path(tempfile.mkdtemp(prefix="p6_notoken_"))
    port = _free_port()
    srv, cfg = _start_with_root(port, root, token=None)
    base = f"http://127.0.0.1:{port}"
    ws = root / "ws3"
    ws.mkdir()
    (ws / "demo.txt").write_bytes(b"hello")
    try:
        status, j = _post(base, "/api/propose", {"goal": "fix hello file", "workspace": str(ws), "file": "demo.txt"})
        assert status == 200
        status, j = _post(base, "/api/execute", {"goal": "fix hello file", "workspace": str(ws), "file": "demo.txt"})
        assert j["status"] == "VERIFIED"
    finally:
        srv.shutdown()
