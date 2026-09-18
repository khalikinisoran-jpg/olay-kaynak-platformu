"""P0-2.1: Connect Claude Code on the initialized Dashboard.

Contract under test: the dashboard exposes a read-only
``claude_connected`` boolean derived from the workspace's
.claude/settings.json Tanuq hook presence; POST /api/connect flips it
to true (idempotently); a corrupted settings file never crashes the
dashboard (fail-safe false); the dashboard never returns settings
content, secrets or tokens. First-run setup flow is untouched.
New test module only (G1: no existing test module modified).
"""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from tanuq import web
from tanuq.config import init_workspace, read_local_token
from tanuq.runtime import load_environment


@pytest.fixture
def connect_server(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "app.py").write_text("value = 1\n", encoding="utf-8", newline="")
    init_workspace(ws)
    env = load_environment(ws)
    token = read_local_token()
    web.SERVICE = web.WorkspaceService(env, token)
    web.SETUP_MODE = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield ws, token, base
    server.shutdown()
    server.server_close()


def _request(base, path, token=None, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, method="POST")
    if token:
        req.add_header("X-TANUQ-Token", token)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body)
        except Exception:
            return exc.code, {"raw": body}


def _dashboard(base, token):
    req = urllib.request.Request(base + "/api/dashboard")
    req.add_header("X-TANUQ-Token", token)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def test_dashboard_starts_not_connected(connect_server):
    ws, token, base = connect_server
    dash = _dashboard(base, token)
    assert dash["claude_connected"] is False
    assert not (ws / ".claude" / "settings.json").exists()


def test_connect_flips_dashboard_to_connected(connect_server):
    ws, token, base = connect_server
    status, _ = _request(base, "/api/connect", token=token,
                         payload={"agent": "claude_code"})
    assert status == 200
    dash = _dashboard(base, token)
    assert dash["claude_connected"] is True
    assert (ws / ".claude" / "settings.json").exists()


def test_reconnect_keeps_dashboard_connected(connect_server):
    ws, token, base = connect_server
    for _ in range(2):
        status, _ = _request(base, "/api/connect", token=token,
                             payload={"agent": "claude_code"})
        assert status == 200
    dash = _dashboard(base, token)
    assert dash["claude_connected"] is True


def test_corrupted_settings_never_crashes_dashboard(connect_server):
    ws, token, base = connect_server
    settings = ws / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text("{not valid json", encoding="utf-8")
    dash = _dashboard(base, token)
    assert dash["claude_connected"] is False
    # the corrupted file is left untouched (fail-safe read, no repair)
    assert settings.read_text(encoding="utf-8") == "{not valid json"


def test_dashboard_never_exposes_settings_content_or_secrets(
        connect_server):
    ws, token, base = connect_server
    secret_command = '"C:\\\\secret-python\\\\python.exe" -m tanuq.claude_code_adapter'
    settings = ws / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps({
        "hooks": {"PreToolUse": [{"matcher": "Edit|Write", "hooks": [
            {"type": "command", "command": secret_command}]}]},
        "some_user_secret_field": "super-secret-value",
    }), encoding="utf-8")
    dash = _dashboard(base, token)
    assert dash["claude_connected"] is True
    raw = json.dumps(dash)
    assert "super-secret-value" not in raw
    assert "some_user_secret_field" not in raw
    assert "secret-python" not in raw
    assert "settings.json" not in raw
    assert set(dash) == {
        "workspace", "protected_scope", "governed",
        "verification_depth", "anchor", "chain_valid", "events",
        "pending_count", "recent_verified", "recent_rolled_back",
        "blocked_count", "incident_count", "critical_incidents",
        "last_terminal", "claude_connected", "limits",
    }


def test_dashboard_connected_reflects_manual_hook_removal(connect_server):
    ws, token, base = connect_server
    _request(base, "/api/connect", token=token,
             payload={"agent": "claude_code"})
    assert _dashboard(base, token)["claude_connected"] is True
    # user removes the Tanuq hook manually -> dashboard reflects reality
    settings = ws / ".claude" / "settings.json"
    settings.write_text(json.dumps({"hooks": {"PreToolUse": []}}),
                        encoding="utf-8")
    assert _dashboard(base, token)["claude_connected"] is False
