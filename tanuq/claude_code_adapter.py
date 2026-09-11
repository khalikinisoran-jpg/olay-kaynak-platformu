"""Tanuq Claude Code PreToolUse vendor adapter.

TRANSLATION LAYER ONLY. This adapter converts Claude Code's
PreToolUse hook input (Edit and Write tool calls) into the existing
generic TANUQ proposal protocol and converts the governed result back
into a PreToolUse decision. It is NOT a governance authority:

- it never grants, consumes, revokes or applies anything
- it never recomputes a governance decision
- it never bypasses the fingerprint/approval/verification chain
- it never returns ``permissionDecision: "allow"`` — every governed
  change is executed exclusively through the TANUQ channel
  (OperationCoordinator.execute -> governed pipeline), so Claude's
  own tool call is always cancelled with an explanatory reason.

Claude Code contract (https://code.claude.com/docs/en/hooks):
- input  : JSON on stdin {session_id, cwd, hook_event_name:
           "PreToolUse", tool_name, tool_input: {...}}
           Edit    : tool_input {file_path, old_string, new_string}
           Write   : tool_input {file_path, content}
- output : exit 0 + JSON {"hookSpecificOutput": {"hookEventName":
           "PreToolUse", "permissionDecision": "deny", ...}}

Everything unknown, malformed or out of scope is fail-closed DENY.

Tool mapping (translation only; the governed chain decides everything
else):
- Edit  -> action "modify" (old_content = old_string,
           new_content = new_string)
- Write -> action "create"  (old_content = "" — the canonical
           no-previous-content marker, new_content = content).
  The governed create validation denies a Write whose target already
  exists (an existing file can never be overwritten through Write;
  Edit governs modifications). Write is therefore HIGH risk and
  always requires human approval through the existing chain.

FAZ 6-lite B (cross-source resume): before proposing, the adapter
correlates the incoming call against EXISTING pending records using
canonical path + exact expected old_content + new_content (+ expected
action). ``reason`` and ``session`` are deliberately NOT correlation
inputs. A single match lets the retry resume the governed execution
under that record's already-registered fingerprint (the pipeline's
approval stage remains the only authorization authority); zero
matches fall back to the normal propose flow; multiple distinct
matches are AMBIGUOUS and fail-closed DENY. Correlation is never an
authorization.
"""
import json

_SUPPORTED_TOOLS = ("Edit", "Write")

# Required tool_input fields per supported tool (vendor contract:
# code.claude.com/docs/en/hooks — tools reference).
_REQUIRED_TOOL_INPUT = {
    "Edit": ("file_path", "old_string", "new_string"),
    "Write": ("file_path", "content"),
}


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
            f"{list(_SUPPORTED_TOOLS)} file changes only"
        )
    if not isinstance(tool_input, dict):
        raise ClaudeHookError("tool_input must be a JSON object")
    for field in _REQUIRED_TOOL_INPUT[tool_name]:
        if field not in tool_input or tool_input[field] is None:
            raise ClaudeHookError(f"missing required tool_input field: {field}")
    parsed = {
        "tool_name": tool_name,
        "file_path": str(tool_input["file_path"]),
        "session_id": str(data.get("session_id", "") or ""),
    }
    if tool_name == "Edit":
        parsed["old_string"] = tool_input["old_string"]
        parsed["new_string"] = tool_input["new_string"]
    else:  # Write
        parsed["content"] = tool_input["content"]
    return parsed


def proposal_payload(parsed):
    """Translate a parsed tool call into the generic proposal schema.

    Edit  -> action "modify" (unchanged behavior).
    Write -> action "create" with the canonical old_content=""
             no-previous-content marker; the governed create chain
             denies an existing target downstream (fail-closed).
    """
    action = "create" if parsed["tool_name"] == "Write" else "modify"
    verb = "write" if parsed["tool_name"] == "Write" else "edit"
    reason = f"claude-code {verb}"
    if parsed.get("session_id"):
        reason = f"claude-code {verb} (session {parsed['session_id']})"
    payload = {
        "path": parsed["file_path"],
        "action": action,
        "reason": reason,
        "new_content": (
            parsed["content"] if parsed["tool_name"] == "Write"
            else parsed["new_string"]
        ),
    }
    if parsed["tool_name"] == "Write":
        payload["old_content"] = ""
    else:
        payload["old_content"] = parsed["old_string"]
    return payload


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


def _expected_correlation(parsed):
    """Expected (action, old_content, new_content) for one parsed call.

    Edit  -> ("modify", old_string, new_string)
    Write -> ("create", "", content) — the governed create marker.

    Used by FAZ 6-lite B correlation so a Write retry can resume a
    pending create record and an Edit retry a pending modify record.
    """
    if parsed["tool_name"] == "Write":
        return "create", "", parsed["content"]
    return "modify", parsed["old_string"], parsed["new_string"]


def _find_pending_match(env, parsed):
    """FAZ 6-lite B correlation: find an EXISTING pending record for
    the same logical change (canonical path + expected action + exact
    old_content + new_content). ``reason`` / ``session`` /
    ``created_at`` are deliberately NOT compared — they are source
    metadata, not the change itself.

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
    expected_action, expected_old, expected_new = _expected_correlation(
        parsed
    )
    matches = []
    for record in load_pending(env.workspace):
        record_path = _canonical(str(record.get("path", "")))
        if record_path is None or record_path != target:
            continue
        if record.get("action", "modify") != expected_action:
            continue
        if record.get("old_content") != expected_old:
            continue
        if record.get("new_content") != expected_new:
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
                f"Tanuq governance DENIED this change: "
                f"{first.get('denial_reason') or first.get('message')}"
            )
        first = proposal["proposals"][0]
        fingerprint = first["fingerprint"]
        result = OperationCoordinator(env).execute(
            fingerprint=fingerprint, session=session_label)

    terminal = result.get("terminal")
    tool_name = parsed["tool_name"]
    if terminal == "VERIFIED":
        return "deny", (
            f"Tanuq: change applied and verified through governed "
            f"execution (fingerprint {fingerprint[:12]}); the "
            f"{tool_name} tool call is unnecessary and was cancelled."
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
            f"Tanuq: pending human approval for this change "
            f"(fingerprint {fingerprint[:12]}). Approve with 'tanuq "
            f"approve' and retry the {tool_name} tool call to resume; "
            f"the tool call itself is cancelled."
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
