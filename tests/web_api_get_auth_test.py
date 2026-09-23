"""A4 HARDENING — sensitive /api/* GET endpoints require the device token.

G1: NEW test module; no existing test module is modified.

Owner decision (A4 = FIX, Option 1): GET /api/pending (and the other
governed view GETs) previously served pending proposal content —
including agent-controlled diff previews — to any local process
without authentication. The existing device-token mechanism
(`_check_token`, constant-time compare) now guards the sensitive
/api/* GET routes with the same fail-closed contract as POST:

1. /api/pending with a valid token        -> 200 + unchanged content
2. /api/pending with a missing token      -> 403, no content leak
3. /api/pending with an invalid token     -> 403, no content leak
4. /api/health without a token            -> 200 (bootstrap exception)
5. static / and /app.js without a token   -> 200 (UI shell)
6. UI-style tokened GET flow              -> 200
7. POST without a token                   -> 403 (existing regression)
8. other sensitive GET (/api/evidence)    -> 403 without a token
"""

import json
import threading
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from tanuq import agent_adapter, web
from tanuq.config import init_workspace
from tanuq.runtime import load_environment


@pytest.fixture
def server(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "demo.txt").write_text("hello", encoding="utf-8", newline="")
    monkeypatch.chdir(ws)
    init_workspace(ws)
    env = load_environment(ws)

    payload = json.dumps([{
        "path": str(ws / "secret-plan.txt"),
        "action": "create",
        "reason": "A4 pending disclosure test",
        "old_content": "",
        "new_content": "token = FAKE-VALUE-FOR-AUDIT",
    }])
    verdict = agent_adapter.propose(env, payload_text=payload)
    assert verdict["proposals"][0]["state"] == "APPROVAL_REQUIRED"

    token = "test-device-token-0123456789abcdef"
    old_service, old_server_token = web.SERVICE, web._server_token
    web.SERVICE = web.WorkspaceService(env, token)
    web._server_token = token

    from http.server import ThreadingHTTPServer

    srv = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}", token
    srv.shutdown()
    srv.server_close()
    thread.join(timeout=5)
    web.SERVICE, web._server_token = old_service, old_server_token


def _get(base, path, token=None):
    headers = {}
    if token is not None:
        headers["X-TANUQ-Token"] = token
    request = Request(base + path, headers=headers)
    try:
        with urlopen(request, timeout=10) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as exc:
        return exc.code, exc.read().decode("utf-8")


# 1. valid token -> 200 + unchanged pending content
def test_pending_with_valid_token_serves_content(server):
    base, token = server
    status, body = _get(base, "/api/pending", token=token)
    assert status == 200
    rows = json.loads(body)["pending"]
    assert rows, "pending proposal missing from authorized view"
    row = rows[0]
    assert row["path"].endswith("secret-plan.txt")
    assert row["risk"] == "HIGH"
    assert "FAKE-VALUE-FOR-AUDIT" in row["diff"]["new_preview"]


# 2. missing token -> 403 fail-closed, no content leak
def test_pending_without_token_is_403(server):
    base, _ = server
    status, body = _get(base, "/api/pending")
    assert status == 403
    assert "FAKE-VALUE-FOR-AUDIT" not in body
    assert "secret-plan" not in body


# 3. invalid token -> 403 fail-closed, no content leak
def test_pending_with_invalid_token_is_403(server):
    base, _ = server
    status, body = _get(base, "/api/pending", token="wrong-token")
    assert status == 403
    assert "FAKE-VALUE-FOR-AUDIT" not in body
    assert "secret-plan" not in body


# 4. /api/health stays tokenless (bootstrap/readiness exception)
def test_health_without_token_stays_available(server):
    base, _ = server
    status, body = _get(base, "/api/health")
    assert status == 200
    assert json.loads(body)["ok"] is True


# 5. static UI shell stays public
def test_static_routes_stay_public(server):
    base, _ = server
    assert _get(base, "/")[0] == 200
    status, body = _get(base, "/app.js")
    assert status == 200
    assert "api(" in body or "fetch" in body


# 6. UI-style tokened GET flow works (dashboard)
def test_tokened_get_flow_works(server):
    base, token = server
    status, body = _get(base, "/api/dashboard", token=token)
    assert status == 200
    assert "governed" in body


# 7. existing POST token enforcement regression
def test_post_without_token_still_403(server):
    base, _ = server
    request = Request(
        base + "/api/execute",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            status = response.status
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8")
    assert status == 403
    assert "fail-closed" in body


# 8. other sensitive GET (/api/evidence) also gated
def test_evidence_get_without_token_is_403(server):
    base, _ = server
    status, _ = _get(base, "/api/evidence")
    assert status == 403
