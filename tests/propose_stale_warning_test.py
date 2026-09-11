"""Propose-stage stale-content early-warning tests.

Real dogfood finding (2/2 runs): a modify proposal whose old_content
is a region (or otherwise does not match the current file) is ACCEPTED
at propose, then DENIED at execute as stale — the user learns the
problem two stages late. This adds read-only early guidance at propose
time WITHOUT changing any governance/validation semantics:

- the proposal is still accepted and governable
- the result carries a "warning" that names the mismatch and the fix
- execute-time stale validation still fail-closed DENIES
- fingerprint/governance behavior is unchanged (the warning is not an
  identity or risk input)
"""
import json

import pytest

from tanuq import agent_adapter
from tanuq.config import init_workspace
from tanuq.runtime import load_environment


@pytest.fixture
def env(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "app.py").write_text(
        "value = 1\n", encoding="utf-8", newline=""
    )
    init_workspace(ws)
    return load_environment(ws)


def _modify(env, old_content):
    return json.dumps({
        "path": str(env.workspace / "app.py"),
        "action": "modify",
        "old_content": old_content,
        "new_content": "value = 2\n",
        "reason": "propose-stage warning test",
    })


def test_full_file_old_content_no_warning(env):
    response = agent_adapter.propose(env, _modify(env, "value = 1\n"))
    result = response["proposals"][0]
    assert result["state"] == "PROPOSED"
    assert "warning" not in result


def test_partial_old_content_propose_warns_but_still_accepted(env):
    response = agent_adapter.propose(env, _modify(env, "value = "))
    result = response["proposals"][0]
    assert result["state"] == "PROPOSED"  # still accepted, not blocked
    warning = result.get("warning")
    assert warning is not None
    assert "does not match the current file content" in warning
    assert "exact current file content" in warning


def test_execute_time_stale_protection_unchanged(env):
    agent_adapter.propose(env, _modify(env, "value = "))
    result = agent_adapter.execute(env)
    assert result["terminal"] == "DENIED"
    assert result["failure_stage"] == "validation"
    assert "Patch is stale" in result["reason"]
    # fail-closed: the file was never modified
    assert (env.workspace / "app.py").read_text(
        encoding="utf-8") == "value = 1\n"


def test_warning_is_not_part_of_fingerprint(env):
    stale = agent_adapter.propose(env, _modify(env, "value = "))
    fp_stale = stale["proposals"][0]["fingerprint"]
    patch = agent_adapter.patch_from_record(
        agent_adapter.load_pending(env.workspace)[0])
    assert patch.fingerprint() == fp_stale
    # the warning is presentation-only: identical proposal JSON yields
    # the identical fingerprint regardless of the on-disk mismatch
    from simulation.agent.worker.patch_proposal import PatchProposal
    same = PatchProposal(
        path=patch.path, action=patch.action, reason=patch.reason,
        old_content=patch.old_content, new_content=patch.new_content,
        allowed_paths=patch.allowed_paths,
    )
    assert same.fingerprint() == fp_stale


def test_missing_file_no_warning(env):
    response = agent_adapter.propose(env, json.dumps({
        "path": str(env.workspace / "ghost.py"),
        "action": "modify",
        "old_content": "x\n",
        "new_content": "y\n",
        "reason": "missing target",
    }))
    result = response["proposals"][0]
    assert result["state"] == "PROPOSED"
    assert "warning" not in result
