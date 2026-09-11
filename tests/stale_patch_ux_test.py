"""Stale-patch DENY UX tests.

Real dogfood finding: a validation-stage DENY (typically a stale
proposal — old_content no longer matches the file) used to surface the
generic "out of scope or policy" guidance, and the history projection
did not show the actual validation failure reason.

This module pins the corrected UX (message-only change; validation,
governance and evidence semantics untouched):
- execute guidance for validation-stage DENY names the REAL validator
  reason and tells the user to resubmit with exact current content
- approval-stage DENY guidance is unchanged
- the history projection surfaces denied_reason (data already carried
  by the existing WorkerPatchValidated event flow)
"""
import json
import subprocess
import sys

import pytest

from tanuq import agent_adapter
from tanuq.config import init_workspace
from tanuq.runtime import load_environment


@pytest.fixture
def env(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "app.py").write_text(
        "def greet(name):\n    return 'Hello, ' + name\n",
        encoding="utf-8",
        newline="",
    )
    init_workspace(ws)
    return load_environment(ws)


def _modify_proposal(env, old_content, new_content=None):
    return json.dumps({
        "path": str(env.workspace / "app.py"),
        "action": "modify",
        "old_content": old_content,
        "new_content": new_content
        if new_content is not None
        else "def greet(name):\n    return 'HI ' + name\n",
        "reason": "stale-patch ux test",
    })


def test_stale_patch_execute_guidance_names_real_validation_reason(env):
    # old_content does NOT match the on-disk file -> stale -> DENY
    agent_adapter.propose(env, _modify_proposal(
        env, "OUTDATED CONTENT THAT WILL NEVER MATCH\n"))
    result = agent_adapter.execute(env)
    assert result["terminal"] == "DENIED"
    assert result["failure_stage"] == "validation"
    guidance = result["guidance"]
    assert "validation failed" in guidance
    assert "Patch is stale" in guidance  # the REAL validator reason
    assert "exact current file content" in guidance
    # the proposal was permanently removed (existing fail-closed rule)
    assert len(agent_adapter.load_pending(env.workspace)) == 0


def test_approval_stage_guidance_unchanged(env):
    # create is HIGH -> approval-stage DENY keeps its own guidance
    agent_adapter.propose(env, json.dumps({
        "path": str(env.workspace / "new.txt"),
        "action": "create",
        "old_content": "",
        "new_content": "content\n",
        "reason": "ux regression guard",
    }))
    result = agent_adapter.execute(env)
    assert result["terminal"] == "DENIED"
    assert result["failure_stage"] == "approval"
    assert "Approval missing or already used" in result["guidance"]
    assert "validation failed" not in result["guidance"]


def test_history_projection_surfaces_denied_reason(env):
    agent_adapter.propose(env, _modify_proposal(
        env, "OUTDATED CONTENT THAT WILL NEVER MATCH\n"))
    agent_adapter.execute(env)
    from tanuq.coordinator import OperationCoordinator
    report = OperationCoordinator(env).operations()
    denied = [op for op in report["operations"] if op["state"] == "DENIED"]
    assert denied, "DENIED operation missing from history"
    reasons = [op.get("denied_reason") for op in denied]
    assert any(r and "Patch is stale" in r for r in reasons), reasons


def test_history_cli_prints_denied_reason(env, tmp_path):
    agent_adapter.propose(env, _modify_proposal(
        env, "OUTDATED CONTENT THAT WILL NEVER MATCH\n"))
    agent_adapter.execute(env)
    proc = subprocess.run(
        [sys.executable, "-m", "tanuq", "history",
         "--workspace", str(env.workspace)],
        capture_output=True, text=True,
    )
    lines = [
        line for line in proc.stdout.splitlines()
        if "denied:" in line
    ]
    assert lines, proc.stdout
    assert any("Patch is stale" in line for line in lines)
