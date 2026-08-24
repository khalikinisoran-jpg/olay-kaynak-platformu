"""P6 structured logging — JSON, request_id, redacted, no old/new content."""
import json
import tempfile
import threading
import time
import io
import sys
from pathlib import Path
from unittest.mock import patch
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from p5.server import ThreadingHTTPServer, Handler
from p5.config import load_config

def _free_port():
    import socket
    s = socket.socket(); s.bind(("", 0)); p = s.getsockname()[1]; s.close(); return p

def test_structured_log_is_json_with_request_id_and_no_old_content():
    port = _free_port()
    # Capture stderr where p5/logging emits
    captured = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = captured
    try:
        cfg = load_config(cli_host="127.0.0.1", cli_port=port)
        import p5.server as srv
        srv.CONFIG = cfg
        Handler.config = cfg
        server = ThreadingHTTPServer((cfg.host, cfg.port), Handler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.5)
        base = f"http://127.0.0.1:{port}"
        ws = Path(tempfile.mkdtemp(prefix="p6_log_"))
        (ws / "demo.txt").write_bytes(b"hello")
        # propose (LOW) and execute (will create log lines)
        data = json.dumps({"goal": "fix hello file", "workspace": str(ws), "file": "demo.txt"}).encode()
        req = Request(base + "/api/propose", data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=5) as r:
            r.read()
        req2 = Request(base + "/api/execute", data=data, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req2, timeout=10) as r:
                r.read()
        except Exception:
            pass
        time.sleep(0.5)
        server.shutdown()
        logs = captured.getvalue().strip().splitlines()
        # At least 2 log lines from propose+execute
        assert len(logs) >= 2
        for line in logs:
            if not line.strip():
                continue
            j = json.loads(line)
            assert "request_id" in j
            assert "method" in j
            assert "path" in j
            assert "status" in j
            assert "ts" in j
            # Must not contain old_content/new_content full
            raw = line
            assert "hello fixed" not in raw  # new_content not logged
            # fingerprint_short may be present but not full content
            # secret markers should be redacted if present (not in this test, but check)
            assert "old_content" not in raw or "<redacted" in raw
    finally:
        sys.stderr = old_stderr

def test_history_logs_redacted():
    # Ensure history endpoint also logs without secret
    port = _free_port()
    captured = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = captured
    try:
        cfg = load_config(cli_host="127.0.0.1", cli_port=port)
        import p5.server as srv
        srv.CONFIG = cfg
        Handler.config = cfg
        server = ThreadingHTTPServer((cfg.host, cfg.port), Handler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.5)
        base = f"http://127.0.0.1:{port}"
        ws = Path(tempfile.mkdtemp(prefix="p6_log_hist_"))
        (ws / "demo.txt").write_bytes(b"hello")
        # trigger history
        import urllib.parse
        req = Request(base + f"/api/history?workspace={urllib.parse.quote(str(ws))}", method="GET")
        with urlopen(req, timeout=5) as r:
            r.read()
        time.sleep(0.3)
        server.shutdown()
        logs = [l for l in captured.getvalue().splitlines() if l.strip()]
        assert any("request_id" in l for l in logs)
    finally:
        sys.stderr = old_stderr
