"""First-run setup endpoint tests (P0-1 Welcome/Setup).

Contract under test: POST /api/setup wraps the EXACT CLI init sequence
(resolve_workspace -> init_workspace -> load_environment ->
ensure_local_token -> register_workspace) and writes ONLY Tanuq's own
init state (config, data dir, anchor key, device token, workspace
registry). It never touches a workspace source file and never invokes
a governance component. New test module only (G1: no existing test
module modified).
"""
import inspect
import json
import os
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from tanuq import web
from tanuq.config import (
    ensure_local_token,
    is_initialized,
    token_path,
)


@pytest.fixture
def setup_server(tmp_path, monkeypatch):
    ws = tmp_path / "fresh"
    ws.mkdir()
    (ws / "notes.txt").write_text("hello", encoding="utf-8", newline="")
    token = ensure_local_token()
    monkeypatch.setattr(web, "SERVICE", None)
    monkeypatch.setattr(web, "SETUP_MODE", True)
    monkeypatch.setattr(web, "SETUP_WS", ws)
    monkeypatch.setattr(web, "_server_token", token)
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    yield ws, token, base
    server.shutdown()
    server.server_close()


def _request(base, path, token=None, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base + path, data=data, method="POST" if data is not None else "GET")
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


def _snapshot(ws: Path):
    out = {}
    for root, _dirs, files in os.walk(ws):
        for name in files:
            p = Path(root) / name
            out[str(p.relative_to(ws))] = p.read_bytes()
    return out


def test_first_run_setup_success(setup_server):
    ws, token, base = setup_server
    status, body = _request(base, "/api/setup", token=token, payload={
        "workspace": str(ws),
        "allowed_paths": [],
        "verification_depth": "compile+tests",
    })
    assert status == 200
    assert body["initialized"] is True
    assert body["workspace"] == str(ws.resolve())
    assert body["allowed_paths"] == [str(ws.resolve())]
    assert body["verification_depth"] == "compile+tests"
    assert body["next"] == "connect-ai"
    assert is_initialized(ws)
    assert (ws / ".tanuq" / "config.json").exists()
    assert (ws / ".tanuq" / "data").is_dir()
    assert token_path().exists()
    # in-place transition: full governed view layer now served
    assert web.SETUP_MODE is False
    assert web.SERVICE is not None


def test_second_setup_rejected_409_config_unchanged(setup_server):
    ws, token, base = setup_server
    status, _ = _request(base, "/api/setup", token=token, payload={
        "workspace": str(ws), "allowed_paths": [], "verification_depth": "compile"})
    assert status == 200
    config_before = (ws / ".tanuq" / "config.json").read_bytes()
    status, body = _request(base, "/api/setup", token=token, payload={
        "workspace": str(ws), "allowed_paths": [], "verification_depth": "compile"})
    assert status == 409
    assert "error" in body
    assert (ws / ".tanuq" / "config.json").read_bytes() == config_before


def test_nonexistent_workspace_rejected(setup_server, tmp_path):
    ws, token, base = setup_server
    missing = tmp_path / "does-not-exist"
    status, body = _request(base, "/api/setup", token=token, payload={
        "workspace": str(missing)})
    assert status == 400
    assert "error" in body
    assert not missing.exists()
    assert not is_initialized(ws)


def test_allowed_path_outside_workspace_rejected(setup_server, tmp_path):
    ws, token, base = setup_server
    outside = tmp_path.parent
    status, body = _request(base, "/api/setup", token=token, payload={
        "workspace": str(ws), "allowed_paths": [str(outside)]})
    assert status == 400
    assert "error" in body
    assert not is_initialized(ws)


def test_invalid_verification_depth_rejected(setup_server):
    ws, token, base = setup_server
    status, body = _request(base, "/api/setup", token=token, payload={
        "workspace": str(ws), "verification_depth": "tests"})
    assert status == 400
    assert "error" in body
    assert not is_initialized(ws)


def test_setup_requires_token_writes_nothing(setup_server):
    ws, token, base = setup_server
    status, body = _request(base, "/api/setup", token=None, payload={
        "workspace": str(ws)})
    assert status == 403
    assert "fail-closed" in body["error"]
    status, body = _request(base, "/api/setup", token="wrong-token", payload={
        "workspace": str(ws)})
    assert status == 403
    assert not (ws / ".tanuq").exists()


def test_local_token_idempotent_through_setup(setup_server):
    ws, token, base = setup_server
    before = token_path().read_bytes()
    status, _ = _request(base, "/api/setup", token=token, payload={
        "workspace": str(ws)})
    assert status == 200
    assert token_path().read_bytes() == before


def test_register_failure_keeps_initialized_state(setup_server, monkeypatch):
    ws, token, base = setup_server

    def boom(_workspace):
        raise RuntimeError("simulated registry failure")

    monkeypatch.setattr("tanuq.config.register_workspace", boom)
    status, body = _request(base, "/api/setup", token=token, payload={
        "workspace": str(ws)})
    assert status == 500
    assert "error" in body
    # partial-failure behavior is the existing CLI behavior: config
    # written, workspace initialized, no invented rollback.
    assert is_initialized(ws)


def test_workspace_source_files_untouched(setup_server):
    ws, token, base = setup_server
    before = _snapshot(ws)
    status, _ = _request(base, "/api/setup", token=token, payload={
        "workspace": str(ws)})
    assert status == 200
    after = _snapshot(ws)
    added = set(after) - set(before)
    assert added == {".tanuq/config.json"} or all(
        k.startswith(".tanuq") for k in added)
    assert set(before) <= set(after)
    for rel, content in before.items():
        assert after[rel] == content


def test_setup_layer_never_references_governance_core():
    src = inspect.getsource(web._setup)
    for forbidden in (
        "FileApplier", "PatchProposal", "ApprovalStore",
        "ApplyAuthorization", "VerificationExecutor",
        "OperationCoordinator", "WorkerActionPipeline",
    ):
        assert forbidden not in src, forbidden


def test_governance_endpoints_fail_closed_after_setup(setup_server):
    ws, token, base = setup_server
    status, _ = _request(base, "/api/setup", token=token, payload={
        "workspace": str(ws)})
    assert status == 200
    status, body = _request(base, "/api/approve", token=None, payload={})
    assert status == 403
    assert "fail-closed" in body["error"]
    status, body = _request(base, "/api/execute", token=None, payload={})
    assert status == 403


def test_setup_mode_governance_gets_are_404_before_setup(setup_server):
    ws, token, base = setup_server
    for path in ("/api/dashboard", "/api/pending", "/api/evidence", "/api/operations"):
        req = urllib.request.Request(base + path)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                code = resp.status
        except urllib.error.HTTPError as exc:
            code = exc.code
        assert code == 404, path
