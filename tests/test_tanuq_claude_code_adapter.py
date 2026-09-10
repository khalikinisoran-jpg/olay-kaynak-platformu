"""Tanuq Claude Code PreToolUse vendor adapter tests.

Contract pinned (https://code.claude.com/docs/en/hooks):
- input : JSON stdin {session_id, cwd, hook_event_name: "PreToolUse",
          tool_name: "Edit", tool_input: {file_path, old_string,
          new_string}}
- output: exit 0 + {"hookSpecificOutput": {"hookEventName":
          "PreToolUse", "permissionDecision": "deny", ...}}

Security invariants: the adapter is a translation layer only (no
grant/consume/apply surface), every unknown/malformed input is
fail-closed DENY, governed changes are executed ONLY through
OperationCoordinator -> agent_adapter, and no secret or patch content
leaks into the decision.
"""
import json
import subprocess
import sys

import pytest

from tanuq import agent_adapter, cli
from tanuq.claude_code_adapter import (
    ClaudeHookError,
    handle_pretooluse,
    parse_pretooluse,
    pretooluse_response,
)
from tanuq.config import init_workspace
from tanuq.runtime import load_environment


@pytest.fixture
def env(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "demo.txt").write_text("hello", encoding="utf-8", newline="")
    monkeypatch.chdir(ws)  # hook entry point resolves workspace = cwd
    init_workspace(ws)
    return load_environment(ws)


def _edit_input(env, old="hello", new='hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
                tool="Edit", **drop):
    ws = env.workspace
    payload = {
        "session_id": "sess-123",
        "hook_event_name": "PreToolUse",
        "tool_name": tool,
        "tool_input": {
            "file_path": str(ws / "demo.txt"),
            "old_string": old,
            "new_string": new,
        },
    }
    for key in drop:
        payload["tool_input"].pop(key, None)
    return json.dumps(payload)


def test_valid_edit_delegates_to_coordinator_and_denies_tool(env):
    from tanuq.coordinator import OperationCoordinator
    calls = {}
    real = OperationCoordinator.execute

    def spy(self, fingerprint=None, run_all=False, session=None):
        calls["fingerprint"] = fingerprint
        calls["session"] = session
        return real(self, fingerprint=fingerprint,
                    run_all=run_all, session=session)

    OperationCoordinator.execute = spy
    try:
        decision, reason = handle_pretooluse(
            env, _edit_input(env, old="hello", new="hello fixed"))
    finally:
        OperationCoordinator.execute = real
    assert decision == "deny"
    assert "applied and verified" in reason
    assert calls["session"] == "sess-123"
    assert len(calls["fingerprint"]) == 64


def test_high_edit_queued_for_approval_and_fail_closed_for_claude(env):
    decision, reason = handle_pretooluse(env, _edit_input(env))
    assert decision == "deny"
    assert "pending human approval" in reason
    # the governed change is NOT applied without approval
    assert (env.workspace / "demo.txt").read_text(
        encoding="utf-8") == "hello"
    records = agent_adapter.load_pending(env.workspace)
    assert len(records) == 1
    assert records[0]["session"] == "sess-123"


def test_verified_edit_applied_through_governed_channel(env):
    target = env.workspace / "demo.txt"
    decision, reason = handle_pretooluse(
        env, _edit_input(env, old="hello", new="hello fixed"))
    assert decision == "deny"
    assert "applied and verified" in reason
    decision, reason = handle_pretooluse(
        env, _edit_input(env, old="hello fixed", new="hello fixed v2"))
    assert decision == "deny"
    assert "applied and verified" in reason
    assert target.read_text(encoding="utf-8") == "hello fixed v2"


def test_approval_denied_is_fail_closed_for_vendor(env):
    proposal = agent_adapter.propose(env, json.dumps({
        "path": str(env.workspace / "demo.txt"),
        "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
        "reason": "cli apply",
    }), session="sess-123")
    agent_adapter.approve(env, proposal["proposals"][0]["fingerprint"])
    # approval consumed by a direct governed execution
    agent_adapter.execute(env, fingerprint=proposal["proposals"][0]["fingerprint"])
    # vendor retries the SAME edit afterwards: a fresh approval is
    # required — the consumed one can never authorize the retry, so
    # the governed run cannot reach VERIFIED again.
    decision, reason = handle_pretooluse(env, _edit_input(env))
    assert decision == "deny"
    assert "terminal state" in reason
    assert "pending human approval" not in reason


def test_malformed_input_fail_closed(env):
    for bad in ("{not json", "[1,2,3]", '"a string"'):
        decision, reason = handle_pretooluse(env, bad)
        assert decision == "deny"
        assert "malformed PreToolUse input" in reason


def test_missing_required_field_fail_closed(env):
    with pytest.raises(ClaudeHookError, match="missing required tool_input field"):
        parse_pretooluse(json.dumps({
            "tool_name": "Edit",
            "tool_input": {"file_path": "x"},
        }))
    decision, reason = handle_pretooluse(env, json.dumps({
        "tool_name": "Edit",
        "tool_input": {"file_path": "x"},
    }))
    assert decision == "deny"
    assert "fail-closed" in reason


def test_unsupported_tool_fail_closed(env):
    decision, reason = handle_pretooluse(env, json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
    }))
    assert decision == "deny"
    assert "unsupported tool" in reason


def test_no_secret_or_content_leakage_in_decision(env):
    decision, reason = handle_pretooluse(env, _edit_input(env))
    assert "sk-test-aaaaaaaaaaaaaaaa" not in reason
    assert "new_string" not in reason and "old_string" not in reason
    response = pretooluse_response(decision, reason)
    dumped = json.dumps(response)
    assert "sk-test-aaaaaaaaaaaaaaaa" not in dumped
    assert response["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_adapter_module_has_no_authority_surface():
    """The adapter's public surface is a fixed translation-only
    whitelist: no grant/approve/apply/revoke authority names can
    appear, and no unexpected public symbol can be added without
    this test failing."""
    import tanuq.claude_code_adapter as adapter

    public = {
        name for name in dir(adapter) if not name.startswith("_")
    }

    assert public == {
        "ClaudeHookError",
        "handle_pretooluse",
        "json",
        "main",
        "parse_pretooluse",
        "pretooluse_response",
        "proposal_payload",
    }

    forbidden = {"grant", "approve", "consume", "revoke", "apply",
                 "write", "execute_pipeline"}

    for name in public:

        assert not any(word in name.lower() for word in forbidden), name


def test_response_contract_matches_claude_code_schema():
    response = pretooluse_response("deny", "because")
    assert response == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "because",
        }
    }


def test_generic_adapter_contract_still_green(env):
    """Existing generic stdin-JSON protocol works alongside the vendor
    adapter (no contract break)."""
    proposal = agent_adapter.propose(env, json.dumps({
        "path": str(env.workspace / "demo.txt"),
        "old_content": "hello", "new_content": "hello generic",
        "reason": "generic",
    }))
    assert proposal["proposals"][0]["state"] == "PROPOSED"




def test_rolled_back_result_maps_to_fail_closed_vendor_response(
        env, monkeypatch):
    """Verification-failure -> ROLLED_BACK result must translate into a
    fail-closed vendor decision (never 'allow')."""
    from tanuq.coordinator import OperationCoordinator
    captured = {}

    def fake_execute(self, fingerprint=None, run_all=False, session=None):
        captured["fingerprint"] = fingerprint
        return {
            "executed": True, "terminal": "ROLLED_BACK",
            "failure_stage": "verification",
            "apply_success": True, "verification_passed": False,
        }

    monkeypatch.setattr(OperationCoordinator, "execute", fake_execute)
    decision, reason = handle_pretooluse(env, _edit_input(
        env, old="hello", new="hello broken"))
    assert decision == "deny"
    assert "rolled back" in reason
    assert captured["fingerprint"]


def test_adapter_preserves_coordinator_result_identity(
        env, monkeypatch):
    """Sentinel identity spy: whatever the coordinator returns, the
    adapter must map it verbatim - never alter or re-classify it."""
    from tanuq.coordinator import OperationCoordinator
    sentinel = {
        "executed": True, "terminal": "VERIFIED",
        "failure_stage": "", "apply_success": True,
        "verification_passed": True,
    }

    def fake_execute(self, fingerprint=None, run_all=False, session=None):
        return dict(sentinel)

    monkeypatch.setattr(OperationCoordinator, "execute", fake_execute)
    decision, reason = handle_pretooluse(
        env, _edit_input(env, old="hello", new="hello fixed"))
    assert decision == "deny"  # vendor contract: always deny the tool
    assert "applied and verified" in reason
    assert "fingerprint" in reason


def test_unsupported_hook_event_name_fail_closed(env):
    with pytest.raises(ClaudeHookError, match="hook_event_name"):
        parse_pretooluse(json.dumps({
            "hook_event_name": "PostToolUse",
            "tool_name": "Edit",
            "tool_input": {"file_path": "x", "old_string": "a",
                           "new_string": "b"},
        }))

# ---- FAZ 6-lite: resume after human approval + pending dedupe ----


def _secret_edit(env, **kwargs):
    return _edit_input(
        env,
        old=kwargs.get("old", "hello"),
        new=kwargs.get(
            "new", 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n'
        ),
    )


def test_rt6_a_approved_retry_resumes_governed_execution(env):
    """RT6-A: after the human grants the fingerprint-bound approval,
    the vendor's retry of the SAME edit resumes the governed execution
    and reaches a REAL VERIFIED (no mock, real verification)."""
    decision, reason = handle_pretooluse(env, _secret_edit(env))
    assert decision == "deny"
    assert "pending human approval" in reason
    pending = agent_adapter.load_pending(env.workspace)
    assert len(pending) == 1
    agent_adapter.approve(env, pending[0]["fingerprint"])
    decision, reason = handle_pretooluse(env, _secret_edit(env))
    assert decision == "deny"
    assert "applied and verified" in reason
    assert (env.workspace / "demo.txt").read_text(
        encoding="utf-8") == 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n'
    # VERIFIED removes the pending record (existing lifecycle)
    assert agent_adapter.load_pending(env.workspace) == []


def test_rt6_b_retry_without_approval_stays_fail_closed(env):
    decision, reason = handle_pretooluse(env, _secret_edit(env))
    assert decision == "deny"
    assert "pending human approval" in reason
    assert (env.workspace / "demo.txt").read_text(
        encoding="utf-8") == "hello"
    records = agent_adapter.load_pending(env.workspace)
    assert len(records) == 1
    assert records[0]["session"] == "sess-123"


def test_rt6_c_retry_does_not_duplicate_pending(env):
    decision, _ = handle_pretooluse(env, _secret_edit(env))
    assert decision == "deny"
    decision, _ = handle_pretooluse(env, _secret_edit(env))
    assert decision == "deny"
    records = agent_adapter.load_pending(env.workspace)
    assert len(records) == 1
    fingerprints = {r["fingerprint"] for r in records}
    assert len(fingerprints) == 1


def test_rt6_d_expired_approval_cannot_resume(env):
    decision, _ = handle_pretooluse(env, _secret_edit(env))
    assert decision == "deny"
    pending = agent_adapter.load_pending(env.workspace)
    record = pending[0]
    # directly grant an already-expired approval for the exact context
    env.approval_store.grant(
        patch_fingerprint=record["fingerprint"],
        path=record["path"],
        action=record["action"],
        risk_level="HIGH",
        attempt=1,
        authorizer="human-operator",
        expires_at="2000-01-01T00:00:00Z",
    )
    decision, reason = handle_pretooluse(env, _secret_edit(env))
    assert decision == "deny"
    assert "pending human approval" in reason
    assert (env.workspace / "demo.txt").read_text(
        encoding="utf-8") == "hello"


def test_rt6_e_wrong_fingerprint_approval_cannot_resume(env):
    decision, _ = handle_pretooluse(env, _secret_edit(env))
    assert decision == "deny"
    # the human approves a DIFFERENT edit (registered directly, never
    # executed): its fingerprint can never authorize the retried edit
    other = agent_adapter.propose(env, json.dumps({
        "path": str(env.workspace / "demo.txt"),
        "old_content": "hello",
        "new_content": "hello v2\n",
        "reason": "rt6-e other edit",
    }), session="sess-123")
    agent_adapter.approve(env, other["proposals"][0]["fingerprint"])
    decision, reason = handle_pretooluse(env, _secret_edit(env))
    assert decision == "deny"
    assert "pending human approval" in reason
    assert (env.workspace / "demo.txt").read_text(
        encoding="utf-8") == "hello"


def test_rt6_f_single_use_approval_cannot_verify_twice(env):
    decision, _ = handle_pretooluse(env, _secret_edit(env))
    assert decision == "deny"
    pending = agent_adapter.load_pending(env.workspace)
    agent_adapter.approve(env, pending[0]["fingerprint"])
    decision, reason = handle_pretooluse(env, _secret_edit(env))
    assert "applied and verified" in reason  # first resume consumes it
    # re-propose the identical edit after VERIFIED: the consumed
    # approval can never authorize a second governed run
    agent_adapter.propose(env, json.dumps({
        "path": str(env.workspace / "demo.txt"),
        "old_content": "hello",
        "new_content": 'hello\napi_key = "sk-test-aaaaaaaaaaaaaaaa"\n',
        "reason": "rt6-f replay attempt",
    }), session="sess-123")
    decision, reason = handle_pretooluse(env, _secret_edit(env))
    assert decision == "deny"
    assert "applied and verified" not in reason
