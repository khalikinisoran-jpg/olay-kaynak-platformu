"""UI static content-type regression tests.

Root cause (fixed): the GET handler served every response with a
hard-coded Content-Type: application/json, so the browser received
the UI index as plain text (nosniff prevented rendering).
Fix: parameterized _headers; index -> text/html, app.js ->
application/javascript, API endpoints unchanged (application/json).
"""
import urllib.request

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


import threading


def _headers(base, path):
    req = urllib.request.Request(base + path)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.status, resp.headers.get("Content-Type", "")


def test_index_served_as_html(ui_server):
    ws, token, base = ui_server
    status, ctype = _headers(base, "/")
    assert status == 200
    assert ctype.startswith("text/html")


def test_appjs_served_as_javascript(ui_server):
    ws, token, base = ui_server
    status, ctype = _headers(base, "/app.js")
    assert status == 200
    assert ctype.startswith("application/javascript")


def test_api_health_stays_json(ui_server):
    ws, token, base = ui_server
    status, ctype = _headers(base, "/api/health")
    assert status == 200
    assert ctype.startswith("application/json")
