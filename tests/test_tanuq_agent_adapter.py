"""Tanuq agent-adapter (hook protocol) tests — Phase 6.

Covers the agent-agnostic CLI/hook contract:
    propose (JSON in -> machine-readable verdict out)
    approve (single-use, fingerprint-bound)
    execute (governed pipeline; VERIFIED / ROLLED_BACK / DENIED)

Only the tanuq/ shell is exercised; the security core itself is
covered by the existing corpus and is not re-tested here.
"""
import json

import pytest

from tanuq import agent_adapter
from tanuq.config import init_workspace, read_local_token
from tanuq.runtime import load_environment


@pytest.fixture
def env(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "demo.txt").write_text("hello", encoding="utf-8", newline="")
    init_workspace(ws)
    return load_environment(ws)


def _propose(env, payload, raw=None):
    text = raw if raw is not None else json.dumps(payload)
    return agent_adapter.propose(env, text)


def test_valid_low_proposal_machine_readable(env):
    response = _propose(env, {
        "path": str(env.workspace / "demo.txt"),
        "old_content": "hello",
        "new_content": "hello fixed",
        "reason": "agent fix",
    })
    proposal = response["proposals"][0]
    assert proposal["state"] == "PROPOSED"
    assert proposal["risk"] == "LOW"
    assert proposal["approval_required"] is False
    assert len(proposal["fingerprint"]) == 64
    assert proposal["denial_reason"] is None
    assert response["denied"] is False
    assert response["pending_count"] == 1


def test_high_proposal_requires_approval(env):
    response = _propose(env, {
        "path": str(env.workspace / "demo.txt"),
        "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
        "reason": "cli apply",
    })
    proposal = response["proposals"][0]
    assert proposal["state"] == "APPROVAL_REQUIRED"
    assert proposal["risk"] == "HIGH"
    assert proposal["approval_required"] is True
    assert "single-use" in proposal["what_this_authorizes"]
    assert "EXACTLY this change" in proposal["what_this_authorizes"]


def test_out_of_scope_denied_and_blocked_evidence(env):
    outside = env.workspace.parent / "outside.txt"
    outside.write_text("hello", encoding="utf-8", newline="")
    response = _propose(env, {
        "path": str(outside),
        "old_content": "hello",
        "new_content": "x",
        "reason": "escape attempt",
    })
    proposal = response["proposals"][0]
    assert proposal["state"] == "DENIED"
    assert proposal["approval_required"] is False
    assert "outside the protected workspace" in proposal["denial_reason"]
    assert response["denied"] is True
    assert response["pending_count"] == 0
    from tanuq.config import tanuq_data_dir
    from tanuq.evidence import blocked_from_events
    blocked = blocked_from_events(tanuq_data_dir(env.workspace))
    assert any(b["path"] == str(outside) for b in blocked)


def test_malformed_json_rejected(env):
    with pytest.raises(agent_adapter.ProtocolError, match="could not be parsed"):
        agent_adapter.propose(env, "{not json")


def test_missing_required_field_rejected(env):
    with pytest.raises(agent_adapter.ProtocolError, match="missing required field: new_content"):
        agent_adapter.propose(env, json.dumps({"path": "x", "old_content": "y"}))


def test_fingerprint_consistency_propose_vs_pending(env):
    payload = {
        "path": str(env.workspace / "demo.txt"),
        "old_content": "hello",
        "new_content": "hello fixed",
        "reason": "agent fix",
    }
    response = _propose(env, payload)
    fp = response["proposals"][0]["fingerprint"]
    pending = agent_adapter.load_pending(env.workspace)
    assert len(pending) == 1
    assert pending[0]["fingerprint"] == fp
    recomputed = agent_adapter.patch_from_record(pending[0]).fingerprint()
    assert recomputed == fp


def test_low_end_to_end_propose_execute_verified(env):
    target = env.workspace / "demo.txt"
    _propose(env, {
        "path": str(target), "old_content": "hello",
        "new_content": "hello fixed", "reason": "agent fix",
    })
    response = agent_adapter.execute(env)
    assert response["executed"] is True
    assert response["terminal"] == "VERIFIED"
    assert response["apply_success"] is True
    assert response["verification_passed"] is True
    assert target.read_text(encoding="utf-8") == "hello fixed"
    assert response["pending_count"] == 0


def test_high_end_to_end_propose_approve_execute_verified(env):
    target = env.workspace / "demo.txt"
    proposal = _propose(env, {
        "path": str(target), "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
        "reason": "cli apply",
    })["proposals"][0]
    denied = agent_adapter.execute(env, proposal["fingerprint"])
    assert denied["terminal"] == "DENIED"
    assert denied["failure_stage"] == "approval"
    grant = agent_adapter.approve(env, proposal["fingerprint"])
    assert grant["count"] == 1
    assert grant["granted"][0]["single_use"] is True
    assert grant["granted"][0]["fingerprint"] == proposal["fingerprint"]
    done = agent_adapter.execute(env, proposal["fingerprint"])
    assert done["terminal"] == "VERIFIED"
    assert "sk-test-aaaaaaaaaaaaaaaa" in target.read_text(encoding="utf-8")


def test_verification_failure_rolls_back(env):
    target = env.workspace / "mod.py"
    target.write_text("x = 1\n", encoding="utf-8", newline="")
    _propose(env, {
        "path": str(target), "old_content": "x = 1\n",
        "new_content": "x = 1\ndef broken(:\n", "reason": "breaking",
    })
    response = agent_adapter.execute(env)
    assert response["terminal"] == "ROLLED_BACK"
    assert response["verification_passed"] is False
    assert target.read_text(encoding="utf-8") == "x = 1\n"


def test_execute_without_pending_reports_error(env):
    response = agent_adapter.execute(env)
    assert response["executed"] is False
    assert response["error"] == "no pending proposals"
