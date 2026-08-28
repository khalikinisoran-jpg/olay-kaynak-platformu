"""P6 secret redaction — synthetic secrets never appear in logs or error responses."""
import json
import tempfile
import threading
import time
import io
import sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from p5.server import ThreadingHTTPServer, Handler
from p5.config import load_config

SYNTH_OPENROUTER = "sk-or-v1-" + "A"*40
SYNTH_CHAIN = "deadbeef" * 8
SYNTH_TOKEN = "p5-local-token-" + "B"*20

def _free_port():
    import socket
    s = socket.socket(); s.bind(("",0)); p=s.getsockname()[1]; s.close(); return p

def test_synthetic_secrets_not_in_logs_or_errors():
    port = _free_port()
    captured = io.StringIO()
    old_stderr = sys.stderr
    sys.stderr = captured
    try:
        # Use synthetic token as local token (secret)
        cfg = load_config(cli_host="127.0.0.1", cli_port=port, cli_token=SYNTH_TOKEN)
        import p5.server as srv
        srv.CONFIG = cfg
        Handler.config = cfg
        server = ThreadingHTTPServer((cfg.host, cfg.port), Handler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        time.sleep(0.5)
        base = f"http://127.0.0.1:{port}"
        ws = Path(tempfile.mkdtemp(prefix="p6_secret_"))
        (ws / "demo.txt").write_bytes(b"hello")
        # Attempt with wrong token — error response should not echo token
        req = Request(base + "/api/approve", data=json.dumps({"workspace": str(ws)}).encode(), headers={"Content-Type": "application/json", "X-P5-Token": "wrong-token"}, method="POST")
        try:
            with urlopen(req, timeout=5) as r:
                r.read()
        except HTTPError as e:
            body = e.read().decode()
            assert SYNTH_TOKEN not in body
            assert "wrong-token" not in body or "missing or invalid" in body
        # Attempt with malformed JSON containing synthetic secret — should not leak
        req2 = Request(base + "/api/propose", data=json.dumps({"goal": f"leak {SYNTH_OPENROUTER}", "workspace": str(ws)}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req2, timeout=5) as r:
                body = r.read().decode()
                assert SYNTH_OPENROUTER not in body
        except HTTPError as e:
            body = e.read().decode()
            assert SYNTH_OPENROUTER not in body
        time.sleep(0.3)
        server.shutdown()
        logs = captured.getvalue()
        # Logs must not contain synthetic secrets
        assert SYNTH_OPENROUTER not in logs
        assert SYNTH_CHAIN not in logs
        assert SYNTH_TOKEN not in logs
        # Also ensure old_content not leaked
        assert "hello fixed" not in logs
    finally:
        sys.stderr = old_stderr

def test_p5_logging_redact_obj():
    from p5.logging import redact_obj
    obj = {"old_content": "secret hello", "new_content": "pwned", "P5_LOCAL_TOKEN": SYNTH_TOKEN, "api_key": "sk-test"}
    red = redact_obj(obj)
    assert "<redacted" in str(red["old_content"])
    assert red["P5_LOCAL_TOKEN"] == "<redacted>"
    assert red["api_key"] == "<redacted>"

def test_error_response_does_not_leak_path():
    port = _free_port()
    cfg = load_config(cli_host="127.0.0.1", cli_port=port)
    import p5.server as srv_mod
    srv_mod.CONFIG = cfg
    Handler.config = cfg
    server = ThreadingHTTPServer((cfg.host, cfg.port), Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)
    base = f"http://127.0.0.1:{port}"
    srv2 = None
    try:
        import tempfile as tf
        root = Path(tf.mkdtemp(prefix="p6_secret_root_"))
        cfg2 = load_config(cli_host="127.0.0.1", cli_port=_free_port(), cli_workspace_root=str(root))
        srv2 = ThreadingHTTPServer((cfg2.host, cfg2.port), Handler)
        Handler.config = cfg2
        srv_mod.CONFIG = cfg2
        t2 = threading.Thread(target=srv2.serve_forever, daemon=True)
        t2.start()
        time.sleep(0.5)
        base2 = f"http://127.0.0.1:{cfg2.port}"
        req = Request(base2 + "/api/propose", data=json.dumps({"goal": "fix", "workspace": "/etc"}).encode(), headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urlopen(req, timeout=5) as r:
                body = r.read().decode()
                assert "/etc" not in body or "outside allowed root" in body  # generic, not raw exception trace
        except HTTPError as e:
            body = e.read().decode()
            assert "Traceback" not in body
        finally:
            if srv2:
                srv2.shutdown()
        server.shutdown()
    except Exception:
        try:
            srv.shutdown()
        except Exception:
            pass
        raise
