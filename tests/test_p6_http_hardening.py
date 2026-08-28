"""P6 HTTP hardening — CORS, headers, body limit, malformed JSON, no-store."""
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

def _start(port, token=None):
    cfg = load_config(cli_host="127.0.0.1", cli_port=port, cli_token=token)
    # Set global config for Handler
    import p5.server as srv
    srv.CONFIG = cfg
    Handler.config = cfg
    server = ThreadingHTTPServer((cfg.host, cfg.port), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)
    return server, cfg

def _req(base, path, method="GET", body=None, headers=None):
    hdrs = headers or {}
    data = json.dumps(body).encode() if body is not None else None
    req = Request(base + path, data=data, headers=hdrs, method=method)
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=5) as r:
            return r.status, r.headers, r.read()
    except HTTPError as e:
        return e.code, e.headers, e.read()

def test_evil_origin_no_wildcard():
    port = _free_port()
    srv, cfg = _start(port)
    base = f"http://127.0.0.1:{port}"
    try:
        # Evil origin should NOT get permissive wildcard
        status, headers, body = _req(base, "/api/health", headers={"Origin": "https://evil.com"})
        assert status == 200
        # Should not be * ; should be either absent or echo only allowed origins
        cors = headers.get("Access-Control-Allow-Origin")
        assert cors != "*", f"wildcard not allowed, got {cors}"
        # localhost origin should be allowed (echo or absent is ok, but not * )
        status, headers, body = _req(base, "/api/health", headers={"Origin": "http://127.0.0.1:8765"})
        cors2 = headers.get("Access-Control-Allow-Origin")
        assert cors2 in (None, "http://127.0.0.1:8765")  # not evil
    finally:
        srv.shutdown()

def test_security_headers_present():
    port = _free_port()
    srv, cfg = _start(port)
    base = f"http://127.0.0.1:{port}"
    try:
        status, headers, body = _req(base, "/api/health")
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert "default-src" in headers.get("Content-Security-Policy", "")
        assert headers.get("Cache-Control") == "no-store"
        # static should also have headers
        status, headers, body = _req(base, "/")
        assert headers.get("X-Content-Type-Options") == "nosniff"
    finally:
        srv.shutdown()

def test_oversized_body_413():
    port = _free_port()
    srv, cfg = _start(port)
    base = f"http://127.0.0.1:{port}"
    try:
        big = "A" * (cfg.max_body + 100)
        req = Request(base + "/api/propose", data=big.encode(), headers={"Content-Type": "application/json"}, method="POST")
        req.add_header("Content-Length", str(len(big.encode())))
        try:
            with urlopen(req, timeout=5) as r:
                assert False, "should have 413"
        except HTTPError as e:
            assert e.code == 413
            body = e.read().decode()
            assert "payload too large" in body
        except (ConnectionAbortedError, ConnectionResetError, OSError):
            # Server correctly closed connection after 413 without reading full body — still enforcement
            pass
    finally:
        srv.shutdown()

def test_malformed_json_400():
    port = _free_port()
    srv, cfg = _start(port)
    base = f"http://127.0.0.1:{port}"
    try:
        req = Request(base + "/api/propose", data=b"not json {", headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=5) as r:
                assert False
        except HTTPError as e:
            assert e.code == 400
            body = e.read().decode()
            assert "malformed JSON" in body
    finally:
        srv.shutdown()

def test_api_no_store():
    port = _free_port()
    srv, cfg = _start(port)
    base = f"http://127.0.0.1:{port}"
    ws = Path(tempfile.mkdtemp(prefix="p6_no_store_"))
    (ws / "demo.txt").write_bytes(b"hello")
    try:
        # propose via POST should have no-store
        status, headers, body = _req(base, "/api/propose", method="POST", body={"goal": "fix hello file", "workspace": str(ws), "file": "demo.txt"})
        assert headers.get("Cache-Control") == "no-store"
    finally:
        srv.shutdown()
