"""Machine-readable `tanuq status --json` tests.

Closes the parity gap: incidents/lineage/export already expose --json,
status did not. Human output is unchanged; --json adds a machine-readable
projection of the same data (view layer only, no governance change).
"""
import json

from tanuq import agent_adapter
from tanuq.cli import cmd_status
from tanuq.config import init_workspace
from tanuq.runtime import load_environment


def _run_status(env, as_json=True):
    import argparse
    import io
    from contextlib import redirect_stdout

    args = argparse.Namespace(
        workspace=str(env.workspace), json=as_json)
    buf = io.StringIO()
    with redirect_stdout(buf):
        cmd_status(args)
    return buf.getvalue()


def _init(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "app.py").write_text("value = 1\n", encoding="utf-8", newline="")
    init_workspace(ws)
    return load_environment(ws)


def test_status_json_reports_core_fields(tmp_path):
    env = _init(tmp_path)
    out = _run_status(env)
    data = json.loads(out)
    assert data["workspace"] == str(env.workspace)
    assert data["governed_mode"] is True
    assert data["evidence"]["chain_valid"] is True
    assert data["evidence"]["anchor"] in ("ACTIVE", "FAILED")
    assert isinstance(data["pending"], list)
    assert isinstance(data["recent_operations"], list)
    assert isinstance(data["incidents"], dict)


def test_status_human_output_unchanged(tmp_path):
    env = _init(tmp_path)
    out = _run_status(env, as_json=False)
    assert "Tanuq status" in out
    assert not out.lstrip().startswith("{")
