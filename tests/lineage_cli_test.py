"""Regression tests: `tanuq lineage` CLI must not crash with --fingerprint.

Found during real dogfood (2026-09): cmd_lineage passed `env` both
positionally (binding to `fingerprint`) and as a keyword argument to
OperationCoordinator.lineage(), raising
TypeError: got multiple values for argument 'fingerprint'.
Read-only CLI/view-layer fix only; lineage semantics untouched.
"""
import argparse
import io
import json
from contextlib import redirect_stdout

from tanuq.cli import cmd_lineage
from tanuq.config import init_workspace
from tanuq.runtime import load_environment


def _args(env, fingerprint=None, as_json=False):
    return argparse.Namespace(
        workspace=str(env.workspace), fingerprint=fingerprint,
        limit=20, json=as_json)


def _run(args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        cmd_lineage(args)
    return buf.getvalue()


def _init(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "app.py").write_text("value = 1\n", encoding="utf-8", newline="")
    init_workspace(ws)
    return load_environment(ws)


def test_lineage_with_fingerprint_filter_does_not_crash(tmp_path):
    env = _init(tmp_path)
    out = _run(_args(env, fingerprint="abc123"))
    assert "Tanuq lineage" in out
    assert "No operations recorded yet." in out


def test_lineage_with_fingerprint_json(tmp_path):
    env = _init(tmp_path)
    out = _run(_args(env, fingerprint="abc123", as_json=True))
    data = json.loads(out)
    assert data["count"] == 0
    assert data["chains"] == []


def test_lineage_without_fingerprint_unchanged(tmp_path):
    env = _init(tmp_path)
    out = _run(_args(env))
    assert "Tanuq lineage" in out
