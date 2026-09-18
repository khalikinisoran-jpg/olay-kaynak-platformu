"""Vendor-independent Connect registry tests (P0-2.1 surface).

Contract under test: /api/connect dispatches through a metadata-only
agent registry (claude_code + generic). Unknown agents are rejected
fail-closed (400) with the supported list. The generic agent requires
no installation — the canonical proposal protocol IS the integration.
Registry entries carry no governance information; the dashboard never
exposes settings content.
New test module only (G1: no existing test module modified).
"""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

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


# ---- B) generic agent ----


def test_generic_connect_returns_protocol_and_writes_nothing(
        connect_server):
    ws, token, base = connect_server
    status, body = _request(base, "/api/connect", token=token,
                            payload={"agent": "generic"})
    assert status == 200
    assert body["connected"] is True
    assert body["agent"] == "generic"
    assert body["proposal_protocol"] == "tanuq propose --stdin-json --json"
    assert body["next"] == "use-canonical-protocol"
    assert not (ws / ".claude").exists()


def test_generic_connect_is_idempotent(connect_server):
    _, token, base = connect_server
    for _ in range(2):
        status, body = _request(base, "/api/connect", token=token,
                                payload={"agent": "generic"})
        assert status == 200
        assert body["proposal_protocol"] == "tanuq propose --stdin-json --json"


# ---- C) unknown agent ----


def test_unknown_agent_rejected_with_supported_list(connect_server):
    ws, token, base = connect_server
    status, body = _request(base, "/api/connect", token=token,
                            payload={"agent": "cursor"})
    assert status == 400
    assert "error" in body
    assert set(body["supported_agents"]) == {"claude_code", "generic"}
    assert not (ws / ".claude").exists()


def test_missing_agent_rejected_with_supported_list(connect_server):
    _, token, base = connect_server
    status, body = _request(base, "/api/connect", token=token, payload={})
    assert status == 400
    assert set(body["supported_agents"]) == {"claude_code", "generic"}


# ---- A) claude regression through the registry ----


def test_claude_connect_through_registry_unchanged(connect_server):
    ws, token, base = connect_server
    status, body = _request(base, "/api/connect", token=token,
                            payload={"agent": "claude_code"})
    assert status == 200
    assert body["connected"] is True
    assert body["agent"] == "claude_code"
    assert body["hook"]["event"] == "PreToolUse"
    settings = ws / ".claude" / "settings.json"
    assert settings.exists()
    hook = json.loads(settings.read_text(encoding="utf-8"))
    assert "tanuq.claude_code_adapter" in json.dumps(hook)


# ---- dashboard metadata ----


def test_dashboard_lists_connectable_agents_without_governance(
        connect_server):
    ws, token, base = connect_server
    dash = _dashboard(base, token)
    agents = {a["agent"]: a for a in dash["connectable_agents"]}
    assert set(agents) == {"claude_code", "generic"}
    assert agents["claude_code"]["requires_install"] is True
    assert agents["claude_code"]["connected"] is False
    assert agents["generic"]["requires_install"] is False
    assert agents["generic"]["proposal_protocol"] == (
        "tanuq propose --stdin-json --json")
    # backward compatibility field still present and consistent
    assert dash["claude_connected"] == agents["claude_code"]["connected"]
    # registry carries no governance vocabulary
    raw = json.dumps(dash["connectable_agents"]).lower()
    for word in ("risk", "policy", "approval", "fingerprint",
                 "authorization"):
        assert word not in raw


def test_dashboard_connected_state_tracks_registry(connect_server):
    ws, token, base = connect_server
    _request(base, "/api/connect", token=token,
             payload={"agent": "claude_code"})
    dash = _dashboard(base, token)
    agents = {a["agent"]: a for a in dash["connectable_agents"]}
    assert agents["claude_code"]["connected"] is True
    assert dash["claude_connected"] is True


# ---- E) UI rendering is registry-driven ----


def test_ui_renders_registry_driven_agent_cards():
    app_js = web.static_bytes("app.js").decode("utf-8")
    # dashboard view consumes the registry metadata, not a hard-coded agent
    assert "connectable_agents" in app_js
    assert "requires_install" in app_js
    assert "data-agent" in app_js
    # connect posts the registry agent id
    assert "JSON.stringify({agent: agent})" in app_js


def test_ui_generic_agent_shows_canonical_protocol():
    app_js = web.static_bytes("app.js").decode("utf-8")
    assert "tanuq propose --stdin-json --json" in app_js
    assert "Connecting an agent is optional" in app_js


def test_setup_card_keeps_claude_default_agent():
    index_html = web.static_bytes("index.html").decode("utf-8")
    assert 'data-agent="claude_code"' in index_html
    assert "data-connect-card" in index_html
