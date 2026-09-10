"""Tanuq Claude Code PreToolUse vendor adapter.

TRANSLATION LAYER ONLY. This adapter converts Claude Code's
PreToolUse hook input (Edit tool calls) into the existing generic
TANUQ proposal protocol and converts the governed result back into a
PreToolUse decision. It is NOT a governance authority:

- it never grants, consumes, revokes or applies anything
- it never recomputes a governance decision
- it never bypasses the fingerprint/approval/verification chain
- it never returns ``permissionDecision: "allow"`` — every governed
  change is executed exclusively through the TANUQ channel
  (OperationCoordinator.execute -> governed pipeline), so Claude's
  own Edit call is always cancelled with an explanatory reason.

Claude Code contract (https://code.claude.com/docs/en/hooks):
- input  : JSON on stdin {session_id, cwd, hook_event_name:
           "PreToolUse", tool_name, tool_input: {file_path,
           old_string, new_string, ...}}
- output : exit 0 + JSON {"hookSpecificOutput": {"hookEventName":
           "PreToolUse", "permissionDecision": "deny", ...}}

Everything unknown, malformed or out of scope is fail-closed DENY.

FAZ 6-lite B (cross-source resume): before proposing, the adapter
correlates the incoming edit against EXISTING pending records using
canonical path + exact old_content + new_content. ``reason`` and
``session`` are deliberately NOT correlation inputs. A single match
lets the retry resume the governed execution under that record's
already-registered fingerprint (the pipeline's approval stage remains
the only authorization authority); zero matches fall back to the
normal propose flow; multiple distinct matches are AMBIGUOUS and
fail-closed DENY. Correlation is never an authorization.
"""
import json

_SUPPORTED_TOOLS = ("Edit",)


class ClaudeHookError(Exception):
    """Malformed or unsupported PreToolUse input (fail-closed)."""


def parse_pretooluse(raw_text):
    """Parse hook stdin. Fail-closed on anything unexpected."""
    try:
        data = json.loads(raw_text)
    except Exception as exc:
        raise ClaudeHookError(f"hook input is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise ClaudeHookError("hook input must be a JSON object")
    hook_event_name = data.get("hook_event_name")
    if hook_event_name not in (None, "PreToolUse"):
        raise ClaudeHookError(
            f"unsupported hook_event_name {hook_event_name!r}: this "
            "adapter only handles PreToolUse"
        )
    tool_name = data.get("tool_name")
    tool_input = data.get("tool_input")
    if tool_name not in _SUPPORTED_TOOLS:
        raise ClaudeHookError(
            f"unsupported tool {tool_name!r}: this adapter governs "
            f"{list(_SUPPORTED_TOOLS)} file edits only"
        )
    if not isinstance(tool_input, dict):
        raise ClaudeHookError("tool_input must be a JSON object")
    for field in ("file_path", "old_string", "new_string"):
        if field not in tool_input or tool_input[field] is None:
            raise ClaudeHookError(f"missing required tool_input field: {field}")
    return {
        "tool_name": tool_name,
        "file_path": str(tool_input["file_path"]),
        "old_string": tool_input["old_string"],
        "new_string": tool_input["new_string"],
        "session_id": str(data.get("session_id", "") or ""),
    }


def proposal_payload(parsed):
    """Translate a parsed Edit call into the generic proposal schema."""
    reason = "claude-code edit"
    if parsed.get("session_id"):
        reason = f"claude-code edit (session {parsed['session_id']})"
    return {
        "path": parsed["file_path"],
        "action": "modify",
        "reason": reason,
        "old_content": parsed["old_string"],
        "new_content": parsed["new_string"],
    }


def pretooluse_response(decision, reason):
    """Build the official PreToolUse structured output (exit 0)."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason,
        }
    }


def _canonical(path_text):
    """Canonical path for correlation, or None if it cannot resolve."""
    from pathlib import Path

    try:
        return str(Path(path_text).resolve())
    except OSError:
        return None


def _find_pending_match(env, parsed):
    """FAZ 6-lite B correlation: find an EXISTING pending record for
    the same logical edit (canonical path + exact old_content +
    new_content). ``reason`` / ``session`` / ``created_at`` are
    deliberately NOT compared — they are source metadata, not the
    change itself.

    Returns ``("matched", fingerprint)`` for exactly one distinct
    matching fingerprint, ``("ambiguous", None)`` for multiple
    distinct fingerprints (fail-closed), or ``("none", None)`` when
    nothing matches. Correlation is NEVER an authorization: the
    fingerprint is only a reference into the governed chain, which
    re-runs validation, governance, approval binding and apply
    authorization itself.
    """
    from tanuq.pending import load_pending

    target = _canonical(parsed["file_path"])
    if target is None:
        return "none", None
    matches = []
    for record in load_pending(env.workspace):
        record_path = _canonical(str(record.get("path", "")))
        if record_path is None or record_path != target:
            continue
        if record.get("old_content") != parsed["old_string"]:
            continue
        if record.get("new_content") != parsed["new_string"]:
            continue
        fingerprint = record.get("fingerprint")
        if fingerprint and fingerprint not in matches:
            matches.append(fingerprint)
    if len(matches) == 1:
        return "matched", matches[0]
    if len(matches) > 1:
        return "ambiguous", None
    return "none", None


def handle_pretooluse(env, raw_text, session=None):
    """Full translation flow: hook stdin -> governed chain -> decision.

    Returns ``(decision, reason)`` where decision is always ``"deny"``
    (the Edit tool call must not run: the change either was executed
    through the Tanuq channel, is queued for human approval, or was
    rejected). Fail-closed on every error path.
    """
    from tanuq import agent_adapter
    from tanuq.coordinator import OperationCoordinator

    payload_text = raw_text
    try:
        parsed = parse_pretooluse(payload_text)
    except ClaudeHookError as exc:
        return "deny", f"Tanuq adapter: malformed PreToolUse input (fail-closed): {exc}"

    payload = json.dumps(proposal_payload(parsed))
    session_label = session or parsed.get("session_id") or None

    # FAZ 6-lite B: correlate against existing pending records first.
    correlation, correlated_fp = _find_pending_match(env, parsed)
    if correlation == "ambiguous":
        return "deny", (
            "Tanuq: multiple pending proposals match this edit; "
            "ambiguous cross-source resume is fail-closed DENY. "
            "Resolve with 'tanuq pending' and 'tanuq execute "
            "--fingerprint'."
        )

    if correlation == "matched":
        # Reuse the already-registered fingerprint; do NOT propose
        # again (no duplicate pending, no second fingerprint). The
        # governed pipeline still re-runs validation, governance and
        # approval binding itself.
        fingerprint = correlated_fp
        result = OperationCoordinator(env).execute(
            fingerprint=fingerprint, session=session_label)
    else:
        proposal = agent_adapter.propose(env, payload, session=session_label)
        if proposal.get("denied"):
            first = proposal["proposals"][0]
            return "deny", (
                f"Tanuq governance DENIED this edit: "
                f"{first.get('denial_reason') or first.get('message')}"
            )
        first = proposal["proposals"][0]
        fingerprint = first["fingerprint"]
        result = OperationCoordinator(env).execute(
            fingerprint=fingerprint, session=session_label)

    terminal = result.get("terminal")
    if terminal == "VERIFIED":
        return "deny", (
            f"Tanuq: change applied and verified through governed "
            f"execution (fingerprint {fingerprint[:12]}); the Edit "
            f"tool call is unnecessary and was cancelled."
        )
    if terminal == "ROLLED_BACK":
        return "deny", (
            f"Tanuq: verification failed for fingerprint "
            f"{fingerprint[:12]}; the change was automatically rolled "
            f"back. See 'tanuq history'."
        )
    if result.get("in_flight"):
        return "deny", (
            f"Tanuq: an execution for fingerprint "
            f"{fingerprint[:12]} is already in flight (fail-closed)."
        )
    if terminal == "DENIED" and result.get("failure_stage") == "approval":
        return "deny", (
            f"Tanuq: pending human approval for this edit "
            f"(fingerprint {fingerprint[:12]}). Approve with 'tanuq "
            f"approve' and retry the edit to resume; the Edit tool "
            f"call itself is cancelled."
        )
    return "deny", (
        f"Tanuq: execution reached terminal state {terminal!r} for "
        f"fingerprint {fingerprint[:12]}; see 'tanuq history'."
    )


def main():
    """Hook entry point: read PreToolUse JSON from stdin, print the
    PreToolUse decision JSON to stdout (exit 0 — the structured JSON
    alone drives the decision, fail-closed DENY on every error)."""
    import contextlib
    import io
    import sys

    from tanuq.runtime import load_environment

    raw = sys.stdin.buffer.read().decode("utf-8")
    try:
        # keep the recovery banner off stdout: Claude Code parses the
        # hook's stdout as the decision JSON
        with contextlib.redirect_stdout(io.StringIO()):
            env = load_environment(None)
    except Exception as exc:
        decision, reason = "deny", (
            f"Tanuq adapter: workspace could not be loaded "
            f"(fail-closed): {exc}"
        )
    else:
        try:
            decision, reason = handle_pretooluse(env, raw)
        except Exception as exc:  # fail-closed: never crash the hook
            decision, reason = "deny", (
                f"Tanuq adapter: unexpected error (fail-closed): {exc}"
            )
    print(json.dumps(pretooluse_response(decision, reason)))
    return 0


if __name__ == "__main__":
    main()
