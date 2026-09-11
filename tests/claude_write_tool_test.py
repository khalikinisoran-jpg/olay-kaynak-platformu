"""Claude Code Write-tool govern-as-create tests.

The Write tool_input schema here follows the OFFICIAL vendor contract
(code.claude.com/docs/en/hooks — tools reference):

    Write: tool_input {file_path: <absolute path>, content: <string>}

(runtime vendor observation is still pending — API credit blocked;
these fixtures encode the documented vendor contract, and the governed
chain re-validates everything downstream regardless).

Invariants pinned:
- Write -> governed create (action="create", old_content="") through
  the frozen fingerprint/approval chain; no new authority, no direct
  filesystem mutation by the adapter
- Write on an EXISTING file is fail-closed DENY (never silently
  converted to modify; Edit governs modifications)
- create is HIGH -> always human approval; no approval / expired /
  consumed approval -> fail-closed DENY
- FAZ 6-lite B correlation: a retried Write resumes its pending
  create record (single match); wrong content/path -> no match;
  multiple distinct matches -> ambiguous fail-closed DENY
- existing Edit->modify behavior is unchanged
"""
import json

import pytest

from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.agent.evidence.worker_events import WorkerEventType

from tanuq import agent_adapter, cli  # noqa: F401  (cli parity)
from tanuq.claude_code_adapter import (
    handle_pretooluse,
    parse_pretooluse,
    proposal_payload,
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


def write_input(env, name="hello_tanuq.txt", content="hi\n", **drop):
    """Vendor-documented Write payload shape (absolute file_path)."""
    tool_input = {
        "content": content,
    }
    if name is not None:
        tool_input["file_path"] = str(env.workspace / name)
    payload = {
        "session_id": "sess-w1",
        "cwd": str(env.workspace),
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": tool_input,
    }
    for key in drop:
        payload["tool_input"].pop(key, None)
    return json.dumps(payload)


# ---------------------------------------------------------------------------
# Parser (vendor-documented schema)
# ---------------------------------------------------------------------------


def test_parse_write_payload_extracts_documented_fields(env):
    parsed = parse_pretooluse(write_input(env))
    assert parsed["tool_name"] == "Write"
    assert parsed["file_path"] == str(env.workspace / "hello_tanuq.txt")
    assert parsed["content"] == "hi\n"


def test_proposal_payload_write_is_create_with_empty_old_content(env):
    parsed = parse_pretooluse(write_input(env))
    payload = proposal_payload(parsed)
    assert payload["path"] == str(env.workspace / "hello_tanuq.txt")
    assert payload["action"] == "create"
    assert payload["old_content"] == ""
    assert payload["new_content"] == "hi\n"


def test_write_missing_content_fail_closed(env):
    decision, reason = handle_pretooluse(env, write_input(env, content=None))
    assert decision == "deny"
    assert "fail-closed" in reason


def test_write_missing_file_path_fail_closed(env):
    decision, reason = handle_pretooluse(
        env, write_input(env, name=None)
    )
    assert decision == "deny"
    assert "fail-closed" in reason


def test_write_malformed_json_fail_closed(env):
    decision, reason = handle_pretooluse(env, "{not json")
    assert decision == "deny"
    assert "fail-closed" in reason


def test_unsupported_tool_still_fail_closed(env):
    decision, reason = handle_pretooluse(env, json.dumps({
        "tool_name": "Bash",
        "tool_input": {"command": "echo hi"},
    }))
    assert decision == "deny"
    assert "unsupported tool" in reason


# ---------------------------------------------------------------------------
# Governance / security
# ---------------------------------------------------------------------------


def test_write_existing_file_is_fail_closed_denied(env):
    decision, reason = handle_pretooluse(
        env, write_input(env, name="demo.txt", content="overwritten?")
    )
    assert decision == "deny"
    # the governed create validation denies the existing target
    assert (env.workspace / "demo.txt").read_text(
        encoding="utf-8") == "hello"


def test_write_out_of_scope_path_denied(env):
    decision, reason = handle_pretooluse(
        env,
        write_input(env, name="../outside_tanuq.txt"),
    )
    assert decision == "deny"
    assert "DENIED" in reason


def test_write_proposal_is_high_and_requires_approval(env):
    decision, reason = handle_pretooluse(env, write_input(env))
    assert decision == "deny"
    assert "pending human approval" in reason
    assert not (env.workspace / "hello_tanuq.txt").exists()
    records = agent_adapter.load_pending(env.workspace)
    assert len(records) == 1
    assert records[0]["action"] == "create"
    assert records[0]["old_content"] == ""


def test_write_without_approval_never_creates_file(env):
    handle_pretooluse(env, write_input(env))
    decision, reason = handle_pretooluse(env, write_input(env))
    assert decision == "deny"
    assert "pending human approval" in reason
    assert not (env.workspace / "hello_tanuq.txt").exists()


def test_write_expired_approval_denied(env):
    handle_pretooluse(env, write_input(env))
    record = agent_adapter.load_pending(env.workspace)[0]
    patch = agent_adapter.patch_from_record(record)
    env.approval_store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action="create",
        risk_level="HIGH",
        attempt=1,
        authorizer="human-operator",
        expires_at=-60,
    )
    decision, reason = handle_pretooluse(env, write_input(env))
    assert decision == "deny"
    assert "pending human approval" in reason
    assert not (env.workspace / "hello_tanuq.txt").exists()


# ---------------------------------------------------------------------------
# FAZ 6-lite B correlation for create records
# ---------------------------------------------------------------------------


def test_write_retry_correlates_single_pending_create(env):
    handle_pretooluse(env, write_input(env))
    assert len(agent_adapter.load_pending(env.workspace)) == 1
    # retry with identical content: single match -> resume the SAME
    # pending fingerprint (no duplicate pending record)
    handle_pretooluse(env, write_input(env))
    assert len(agent_adapter.load_pending(env.workspace)) == 1


def test_write_wrong_content_does_not_correlate(env):
    handle_pretooluse(env, write_input(env))
    decision, reason = handle_pretooluse(
        env, write_input(env, content="different\n")
    )
    assert decision == "deny"
    records = agent_adapter.load_pending(env.workspace)
    assert len(records) == 2  # no match -> normal propose -> new record
    fingerprints = {r["fingerprint"] for r in records}
    assert len(fingerprints) == 2


def test_write_wrong_path_does_not_correlate(env):
    handle_pretooluse(env, write_input(env, name="one.txt"))
    handle_pretooluse(env, write_input(env, name="two.txt"))
    records = agent_adapter.load_pending(env.workspace)
    assert {r["path"] for r in records} == {
        str(env.workspace / "one.txt"),
        str(env.workspace / "two.txt"),
    }


def test_write_ambiguous_correlation_fail_closed(env):
    from tanuq.pending import save_pending

    target = env.workspace / "hello_tanuq.txt"
    same_content = "dup\n"
    save_pending(env.workspace, [
        PatchProposal(
            path=str(target),
            action="create",
            reason="source A",
            old_content="",
            new_content=same_content,
            allowed_paths=tuple(env.config.allowed_paths),
        ),
        PatchProposal(
            path=str(target),
            action="create",
            reason="source B",
            old_content="",
            new_content=same_content,
            allowed_paths=tuple(env.config.allowed_paths),
        ),
    ])
    decision, reason = handle_pretooluse(env, write_input(
        env, content=same_content))
    assert decision == "deny"
    assert "ambiguous" in reason


# ---------------------------------------------------------------------------
# End-to-end: Write -> approval -> governed create -> VERIFIED
# ---------------------------------------------------------------------------


def test_write_full_governed_chain_verified(env):
    target = env.workspace / "hello_tanuq.txt"
    # 1. Write arrives -> governed proposal -> HIGH -> approval stage
    decision, reason = handle_pretooluse(env, write_input(env))
    assert decision == "deny"
    assert "pending human approval" in reason
    assert not target.exists()
    # 2. human approval (single-use, fingerprint-bound)
    granted = agent_adapter.approve(env)
    assert granted["count"] == 1
    assert granted["granted"][0]["risk"] == "HIGH"
    assert granted["granted"][0]["single_use"] is True
    # 3. retried Write -> correlation resumes the governed execution
    decision, reason = handle_pretooluse(env, write_input(env))
    assert decision == "deny"
    assert "applied and verified" in reason
    # 4. the file exists with the EXACT approved content
    assert target.read_text(encoding="utf-8") == "hi\n"
    # 5. governed chain state is clean
    assert len(agent_adapter.load_pending(env.workspace)) == 0


def test_write_governed_execution_consumes_approval_single_use(env):
    target = env.workspace / "hello_tanuq.txt"
    handle_pretooluse(env, write_input(env))
    assert agent_adapter.approve(env)["count"] == 1
    decision, reason = handle_pretooluse(env, write_input(env))
    assert "applied and verified" in reason
    assert target.exists()
    # a third identical Write has no pending record and no approval;
    # and since the file NOW EXISTS, governed create validation
    # fail-closed DENIES it (existing target is never overwritten)
    decision, reason = handle_pretooluse(env, write_input(env))
    assert decision == "deny"
    assert "DENIED" in reason
    assert target.read_text(encoding="utf-8") == "hi\n"


def test_write_evidence_records_create_action(env):
    handle_pretooluse(env, write_input(env))
    pending_fp = agent_adapter.load_pending(env.workspace)[0]["fingerprint"]
    agent_adapter.approve(env)
    handle_pretooluse(env, write_input(env))
    proposed = [
        e for e in env.kernel.events
        if e.event_type == WorkerEventType.PATCH_PROPOSED
    ]
    assert proposed
    assert all(e.payload["action"] == "create" for e in proposed)
    validated = [
        e for e in env.kernel.events
        if e.event_type == WorkerEventType.PATCH_VALIDATED
    ]
    assert validated
    assert validated[-1].payload["patch_fingerprint"] == pending_fp


# ---------------------------------------------------------------------------
# Edit behavior unchanged (regression guard inside this module)
# ---------------------------------------------------------------------------


def test_edit_flow_unchanged_low_risk_auto_verified(env):
    target = env.workspace / "demo.txt"
    decision, reason = handle_pretooluse(
        env, json.dumps({
            "session_id": "sess-e1",
            "hook_event_name": "PreToolUse",
            "tool_name": "Edit",
            "tool_input": {
                "file_path": str(target),
                "old_string": "hello",
                "new_string": "hello fixed",
            },
        }))
    assert decision == "deny"
    assert "applied and verified" in reason
    assert target.read_text(encoding="utf-8") == "hello fixed"
