"""Tanuq product-UI tests (Phase 4-5).

Covers only the tanuq/ web shell: token auth (fail-closed), governed
default, anchor default, pending/approve/execute lifecycle, single-use
approval, reject, blocked-actions evidence, verification rollback
visibility. Core security behavior is covered by the existing corpus
and is intentionally not re-tested.
"""
import json
import threading
import urllib.request
import urllib.error

import pytest

from tanuq import web
from tanuq.config import init_workspace, read_local_token
from tanuq.runtime import load_environment


@pytest.fixture
def ui_server(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "demo.txt").write_text("hello", encoding="utf-8", newline="")
    init_workspace(ws)
    env = load_environment(ws)
    token = read_local_token()

    web.SERVICE = web.WorkspaceService(env, token)
    from http.server import ThreadingHTTPServer
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield ws, token, base
    server.shutdown()
    server.server_close()


def _request(base, path, token=None, payload=None, method=None):
    url = base + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data is not None else "GET"))
    if token:
        req.add_header("X-TANUQ-Token", token)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        try:
            return exc.code, json.loads(body)
        except Exception:
            return exc.code, {"raw": body}


def test_all_state_changing_posts_require_token(ui_server):
    ws, token, base = ui_server
    for path, payload in [
        ("/api/propose", {"path": str(ws / "demo.txt"), "old_content": "hello", "new_content": "x"}),
        ("/api/approve", {}),
        ("/api/reject", {"fingerprint": "abc"}),
        ("/api/execute", {}),
    ]:
        status, body = _request(base, path, token=None, payload=payload)
        assert status == 403, path
        assert "fail-closed" in body["error"]
        status, body = _request(base, path, token="wrong-token-value", payload=payload)
        assert status == 403, path


def test_health_reports_governed_and_anchor_active(ui_server):
    ws, token, base = ui_server
    status, body = _request(base, "/api/health")
    assert status == 200
    assert body["governed"] is True
    assert body["anchor"] == "ACTIVE"
    assert body["limits"]["os_sandbox"] is False
    assert body["limits"]["network_enforcement"] is False


def test_full_ui_lifecycle_low_auto_high_replay(ui_server):
    ws, token, base = ui_server
    target = str(ws / "demo.txt")
    status, body = _request(base, "/api/propose", token=token, payload={
        "path": target, "old_content": "hello", "new_content": "hello fixed", "reason": "ui test",
    })
    assert status == 200
    low = body["proposals"][0]
    assert low["state"] == "PROPOSED"
    assert low["risk"] == "LOW"
    status, body = _request(base, "/api/execute", token=token, payload={})
    assert body["terminal"] == "VERIFIED"
    assert (ws / "demo.txt").read_text(encoding="utf-8") == "hello fixed"

    secret_new = 'hello fixed\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n'
    status, body = _request(base, "/api/propose", token=token, payload={
        "path": target, "old_content": "hello fixed", "new_content": secret_new, "reason": "ui test",
    })
    high = body["proposals"][0]
    assert high["state"] == "APPROVAL_REQUIRED"
    assert high["risk"] == "HIGH"
    assert "single-use" in high["what_this_authorizes"]
    assert "EXACTLY this change" in high["what_this_authorizes"]

    status, body = _request(base, "/api/execute", token=token, payload={})
    assert body["terminal"] == "DENIED"
    assert body["failure_stage"] == "approval"

    status, body = _request(base, "/api/approve", token=token, payload={"fingerprint": high["fingerprint"]})
    assert body["count"] == 1
    assert body["granted"][0]["single_use"] is True

    status, body = _request(base, "/api/execute", token=token, payload={"fingerprint": high["fingerprint"]})
    assert body["terminal"] == "VERIFIED"

    status, body = _request(base, "/api/activity", token=token)
    terminals = [i["terminal"] for i in body["intents"]]
    assert "VERIFIED" in terminals


def test_propose_out_of_scope_records_blocked_evidence(ui_server):
    ws, token, base = ui_server
    outside = str(ws.parent / "outside.txt")
    status, body = _request(base, "/api/propose", token=token, payload={
        "path": outside, "old_content": "hello", "new_content": "x", "reason": "escape",
    })
    assert body["proposals"][0]["state"] == "DENIED"
    status, body = _request(base, "/api/blocked", token=token)
    assert any(b["path"] == outside for b in body["blocked"])


def test_reject_removes_pending(ui_server):
    ws, token, base = ui_server
    target = str(ws / "demo.txt")
    _request(base, "/api/propose", token=token, payload={
        "path": target, "old_content": "hello", "new_content": "hello!\n", "reason": "r",
    })
    status, body = _request(base, "/api/pending", token=token)
    assert len(body["pending"]) == 1
    fp = body["pending"][0]["fingerprint"]
    status, body = _request(base, "/api/reject", token=token, payload={"fingerprint": fp})
    assert body["removed"] == 1
    status, body = _request(base, "/api/pending", token=token)
    assert body["pending"] == []


def test_verification_failure_visible_as_rolled_back(ui_server):
    ws, token, base = ui_server
    mod = ws / "mod.py"
    mod.write_text("x = 1\n", encoding="utf-8", newline="")
    _request(base, "/api/propose", token=token, payload={
        "path": str(mod), "old_content": "x = 1\n", "new_content": "x = 1\ndef broken(:\n", "reason": "breaking",
    })
    status, body = _request(base, "/api/execute", token=token, payload={})
    assert body["terminal"] == "ROLLED_BACK"
    assert mod.read_text(encoding="utf-8") == "x = 1\n"


def test_evidence_endpoint_reports_chain_and_anchor(ui_server):
    ws, token, base = ui_server
    status, body = _request(base, "/api/evidence", token=token)
    assert body["chain_valid"] is True
    assert body["anchor"] == "ACTIVE"
    assert "tamper-evident" in body["note"]
    assert isinstance(body["rows"], list)


def test_dashboard_shows_governed_active(ui_server):
    ws, token, base = ui_server
    status, body = _request(base, "/api/dashboard", token=token)
    assert body["governed"] is True
    assert body["anchor"] == "ACTIVE"
    assert body["limits"]["os_sandbox"] is False


def test_execute_endpoint_uses_coordinator_delegation(ui_server, monkeypatch):
    ws, token, base = ui_server
    import tanuq.coordinator as coord_module

    calls = {}
    sentinel = {"executed": True, "terminal": "FAKE_TERMINAL"}

    class FakeCoordinator:
        def __init__(self, env):
            calls["env"] = env
        def execute(self, fingerprint=None, run_all=False, session=None):
            calls.update(fingerprint=fingerprint, run_all=run_all,
                         session=session)
            return sentinel

    monkeypatch.setattr(
        coord_module, "OperationCoordinator", FakeCoordinator
    )
    status, body = _request(base, "/api/execute", token=token, payload={})
    assert status == 200
    assert body == sentinel
    assert calls["run_all"] is False
    assert calls["session"] is None


def test_execute_endpoint_conflict_returns_409(ui_server, monkeypatch):
    ws, token, base = ui_server
    import tanuq.coordinator as coord_module

    class BusyCoordinator:
        def __init__(self, env):
            pass
        def execute(self, fingerprint=None, run_all=False, session=None):
            return {"executed": False, "in_flight": True,
                    "error": "an execution for this selector is already "
                             "in flight", "terminal": None}

    monkeypatch.setattr(
        coord_module, "OperationCoordinator", BusyCoordinator
    )
    status, body = _request(base, "/api/execute", token=token, payload={})
    assert status == 409
    assert body["in_flight"] is True


def test_execute_endpoint_cannot_bypass_governance(ui_server):
    ws, token, base = ui_server
    target = str(ws / "demo.txt")
    status, body = _request(base, "/api/propose", token=token, payload={
        "path": target, "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
        "reason": "cli apply",
    })
    assert body["proposals"][0]["state"] == "APPROVAL_REQUIRED"
    status, body = _request(base, "/api/execute", token=token, payload={})
    assert body["terminal"] == "DENIED"
    assert body["failure_stage"] == "approval"
    assert (ws / "demo.txt").read_text(encoding="utf-8") == "hello"
