"""Connect-AI endpoint tests (P0-2).

Contract under test: POST /api/connect installs the governed Claude
Code PreToolUse hook (Edit|Write) into <workspace>/.claude/settings.json
and touches NOTHING else. Existing user settings and unrelated hooks
are preserved (semantic merge); TANUQ hook insertion is idempotent;
malformed existing JSON is never overwritten (fail-closed 409); the
hook command uses the interpreter this server runs under
(sys.executable). The endpoint never enters the governance chain.
New test module only (G1: no existing test module modified).
"""
import inspect
import json
import os
import sys
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


def _settings(ws: Path):
    return json.loads(
        (ws / ".claude" / "settings.json").read_text(encoding="utf-8"))


def _snapshot(root: Path):
    out = {}
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            p = Path(dirpath) / name
            out[str(p.relative_to(root))] = p.read_bytes()
    return out


def test_connect_creates_settings_with_correct_hook(connect_server):
    ws, token, base = connect_server
    assert not (ws / ".claude").exists()
    status, body = _request(base, "/api/connect", token=token,
                            payload={"agent": "claude_code"})
    assert status == 200
    assert body["connected"] is True
    assert body["agent"] == "claude_code"
    assert body["hook"] == {"event": "PreToolUse", "matcher": "Edit|Write"}
    assert body["next"] == "open-claude-code"
    settings = _settings(ws)
    entry = settings["hooks"]["PreToolUse"][0]
    assert entry["matcher"] == "Edit|Write"
    sub = entry["hooks"][0]
    assert sub["type"] == "command"
    assert sub["command"] == f'"{sys.executable}" -m tanuq.claude_code_adapter'


def test_connect_preserves_existing_settings_and_hooks(connect_server):
    ws, token, base = connect_server
    user_settings = {
        "model": "opus",
        "permissions": {"allow": ["Bash(git status)"]},
        "hooks": {
            "PreToolUse": [{"matcher": "Bash", "hooks": [
                {"type": "command", "command": "my-own-hook.exe"}]}],
            "PostToolUse": [{"matcher": "Edit", "hooks": [
                {"type": "command", "command": "post-hook.exe"}]}],
        },
    }
    (ws / ".claude").mkdir()
    (ws / ".claude" / "settings.json").write_text(
        json.dumps(user_settings, indent=2), encoding="utf-8")
    status, _ = _request(base, "/api/connect", token=token,
                         payload={"agent": "claude_code"})
    assert status == 200
    settings = _settings(ws)
    # user keys preserved semantically
    assert settings["model"] == "opus"
    assert settings["permissions"] == user_settings["permissions"]
    assert settings["hooks"]["PostToolUse"] == user_settings["hooks"]["PostToolUse"]
    # the user's own PreToolUse hook is still there, next to the TANUQ one
    matchers = [e.get("matcher") for e in settings["hooks"]["PreToolUse"]]
    assert "Bash" in matchers and "Edit|Write" in matchers


def test_connect_is_idempotent(connect_server):
    ws, token, base = connect_server
    _request(base, "/api/connect", token=token, payload={"agent": "claude_code"})
    first = (ws / ".claude" / "settings.json").read_bytes()
    status, _ = _request(base, "/api/connect", token=token,
                         payload={"agent": "claude_code"})
    assert status == 200
    assert (ws / ".claude" / "settings.json").read_bytes() == first
    settings = _settings(ws)
    assert len(settings["hooks"]["PreToolUse"]) == 1


def test_connect_updates_stale_tanuq_command_in_place(connect_server):
    ws, token, base = connect_server
    (ws / ".claude").mkdir()
    (ws / ".claude" / "settings.json").write_text(json.dumps({
        "hooks": {"PreToolUse": [{"matcher": "Edit|Write", "hooks": [
            {"type": "command", "command": "C:\\OLD\\python.exe -m tanuq.claude_code_adapter"}]}]}
    }), encoding="utf-8")
    status, _ = _request(base, "/api/connect", token=token,
                         payload={"agent": "claude_code"})
    assert status == 200
    entry = _settings(ws)["hooks"]["PreToolUse"]
    assert len(entry) == 1
    assert entry[0]["hooks"][0]["command"] == (
        f'"{sys.executable}" -m tanuq.claude_code_adapter')


def test_connect_malformed_settings_refused_unchanged(connect_server):
    ws, token, base = connect_server
    (ws / ".claude").mkdir()
    broken = b'{"hooks": {"PreToolUse": [ broken'
    (ws / ".claude" / "settings.json").write_bytes(broken)
    status, body = _request(base, "/api/connect", token=token,
                            payload={"agent": "claude_code"})
    assert status == 409
    assert "error" in body
    assert (ws / ".claude" / "settings.json").read_bytes() == broken


def test_connect_requires_token(connect_server):
    ws, token, base = connect_server
    for tok in (None, "wrong-token"):
        status, body = _request(base, "/api/connect", token=tok,
                                payload={"agent": "claude_code"})
        assert status == 403
        assert "fail-closed" in body["error"]
    assert not (ws / ".claude").exists()


def test_connect_unsupported_agent_rejected(connect_server):
    ws, token, base = connect_server
    status, body = _request(base, "/api/connect", token=token,
                            payload={"agent": "cursor"})
    assert status == 400
    assert "error" in body
    assert not (ws / ".claude").exists()


def test_connect_write_failure_keeps_existing_settings(
        connect_server, monkeypatch):
    ws, token, base = connect_server
    (ws / ".claude").mkdir()
    original = b'{"model": "opus"}'
    (ws / ".claude" / "settings.json").write_bytes(original)

    real_replace = Path.replace

    def boom(self, target):
        raise PermissionError("simulated write failure")

    monkeypatch.setattr(Path, "replace", boom)
    status, body = _request(base, "/api/connect", token=token,
                            payload={"agent": "claude_code"})
    monkeypatch.setattr(Path, "replace", real_replace)
    assert status == 500
    assert "error" in body
    assert (ws / ".claude" / "settings.json").read_bytes() == original
    assert not (ws / ".claude" / "settings.tmp").exists()


def test_connect_touches_only_claude_dir(connect_server):
    ws, token, base = connect_server
    tanuq_before = _snapshot(ws / ".tanuq")
    status, _ = _request(base, "/api/connect", token=token,
                         payload={"agent": "claude_code"})
    assert status == 200
    # source files untouched
    assert (ws / "app.py").read_text(encoding="utf-8") == "value = 1\n"
    assert sorted(p.name for p in ws.iterdir()) == [".claude", ".tanuq", "app.py"]
    # governance state untouched
    assert _snapshot(ws / ".tanuq") == tanuq_before


def test_connect_never_references_governance_core():
    src = inspect.getsource(web._connect)
    for forbidden in (
        "FileApplier", "PatchProposal", "ApprovalStore",
        "ApplyAuthorization", "VerificationExecutor",
        "OperationCoordinator", "WorkerActionPipeline",
    ):
        assert forbidden not in src, forbidden


def test_connect_unavailable_in_setup_mode(tmp_path, monkeypatch):
    ws = tmp_path / "fresh"
    ws.mkdir()
    token = read_local_token()
    monkeypatch.setattr(web, "SERVICE", None)
    monkeypatch.setattr(web, "SETUP_MODE", True)
    monkeypatch.setattr(web, "_server_token", token)
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        status, _ = _request(base, "/api/connect", token=token,
                             payload={"agent": "claude_code"})
        assert status == 404
    finally:
        server.shutdown()
        server.server_close()
