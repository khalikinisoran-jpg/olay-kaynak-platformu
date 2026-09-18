# Tanuq — Agent Integration Protocol

Tanuq is an **agent-agnostic governance gateway**. Any AI coding agent
(Claude Code, Codex, Cursor, OpenHands, Aider, a custom script, …) can
submit file-change proposals through one generic CLI/hook protocol —
no native integration or Python knowledge required.

> Tanuq never claims native support for a specific commercial agent.
> The protocol below is the verified integration surface; per-agent
> support is proven per agent, not assumed.

---

## The protocol in one picture

```
AI AGENT
   │  propose (JSON on stdin)
   ▼
tanuq propose --stdin-json --json
   │  deterministic governance (scope + risk + policy)
   ▼
┌─────────────────────────────────────────────┐
│ PROPOSED (LOW/MEDIUM)  → tanuq execute     │ → VERIFIED / ROLLED_BACK
│ APPROVAL_REQUIRED (HIGH/CRITICAL)           │
│   → operator: tanuq approve                │
│   → tanuq execute → VERIFIED               │
│ DENIED (out of scope / policy / unknown)    │ → blocked evidence
└─────────────────────────────────────────────┘
```

The agent only ever calls three commands:

| Command | Purpose | Exit code |
|---|---|---|
| `tanuq propose --workspace WS --stdin-json [--json]` | Submit proposal(s); machine-readable verdict with `--json` | `0` accepted · `1` denied/error |
| `tanuq approve --workspace WS [--fingerprint FP]` | Operator grants a single-use approval (HIGH/CRITICAL only) | `0` granted · `1` none granted |
| `tanuq execute --workspace WS [--fingerprint FP] [--all]` | Run pending proposal(s) through the governed pipeline | `0` VERIFIED · `1` otherwise |

`--workspace` may be omitted when the current directory is the
initialized workspace.

---

## Proposal input (stdin JSON)

One proposal object or an array of objects:

```json
{
  "path": "C:/absolute/path/to/workspace/src/app.py",
  "old_content": "exact current file content",
  "new_content": "proposed new content",
  "reason": "short human-readable reason",
  "action": "modify"
}
```

Rules:

- `path`, `old_content`, `new_content` are **required**. Missing →
  `ProtocolError` (exit 1, stderr message).
- `action` must be `"modify"` (the product currently governs file
  modifications only).
- `path` must be absolute (or the agent uses the human flag form
  `--file`). Out-of-workspace paths are DENIED.
- `old_content` must exactly match the file on disk at execution time;
  a stale proposal is rejected by validation (fail-closed).
- `reason` is part of the approval fingerprint: after an approval, the
  proposal must be re-submitted identically; changing anything changes
  the fingerprint and invalidates the approval.

## Verdict output (`--json`)

```json
{
  "proposals": [
    {
      "path": ".../demo.txt",
      "action": "modify",
      "reason": "agent fix",
      "fingerprint": "64-hex sha256 of the exact proposal",
      "fingerprint_short": "4bdbba290d9f",
      "diff": {"old_preview": "...", "new_preview": "...", "old_len": 5, "new_len": 11},
      "state": "PROPOSED | APPROVAL_REQUIRED | DENIED",
      "risk": "LOW | MEDIUM | HIGH | CRITICAL | UNKNOWN",
      "approval_required": false,
      "reason": "deterministic governance reason",
      "denial_reason": null,
      "message": "human-readable summary",
      "governance": {"risk": "LOW", "allowed": true, "approval_required": false, "reason": "..."},
      "what_this_authorizes": null
    }
  ],
  "denied": false,
  "pending_count": 1
}
```

Guaranteed machine-readable fields per proposal:
`state`, `risk`, `fingerprint`, `approval_required`,
`reason` / `denial_reason` (exactly one is meaningful), `message`.
For `APPROVAL_REQUIRED`, `what_this_authorizes` spells out precisely
what an approval would bind to.

### Examples

**LOW (auto-apply eligible):**

```json
{"state": "PROPOSED", "risk": "LOW", "approval_required": false,
 "message": "Risk: LOW — accepted; it will apply on execute with verification and rollback."}
```

**HIGH (approval required):**

```json
{"state": "APPROVAL_REQUIRED", "risk": "HIGH", "approval_required": true,
 "message": "Risk: HIGH — approval required (single-use, fingerprint-bound, TTL 3600s).",
 "what_this_authorizes": "Approving authorizes EXACTLY this change: modify on .../demo.txt ... single-use (expires 3600s after granting)."}
```

**DENIED (out of scope):**

```json
{"state": "DENIED", "risk": "UNKNOWN", "approval_required": false,
 "denial_reason": "outside the protected workspace (Patch path is outside the allowed scope.)",
 "message": "DENIED: outside the protected workspace (...)"}
```

Denied proposals are never executed; the denial itself is recorded as
tamper-evident blocked-action evidence (visible in the UI's Blocked
Actions screen and in the event chain).

## Approval flow (operator)

Approvals are **single-use**, **fingerprint-bound** and expire after
3600 s. One approval authorizes exactly one execution of exactly the
approved content:

```bash
tanuq approve --workspace WS                # all pending risky proposals
tanuq approve --workspace WS --fingerprint 3fb6e981
```

An agent that wants a previously approved change applied again must
re-propose and obtain a fresh approval. There is no bypass flag.

## Execution result

`tanuq execute` prints a human summary; the agent observes the
outcome by exit code and the terminal state:

| Terminal | Meaning | Exit |
|---|---|---|
| `VERIFIED` | applied + verification passed | 0 |
| `ROLLED_BACK` | verification failed → change automatically reverted | 1 |
| `DENIED` (approval) | approval missing/expired/already consumed | 1 |
| `DENIED` (validation/risk) | out of scope or policy → removed from queue | 1 |
| `FAILED` / `ROLLBACK_FAILED` | operation did not reach a verified state | 1 |

Every outcome (including rollbacks and denials) is appended to the
hash-chained, anchored evidence journals and is visible via
`tanuq history` / `tanuq verify` / the UI.

### Execution orchestration (OperationCoordinator)

Both `tanuq execute` (CLI) and `POST /api/execute` (Web UI) route
through a single orchestration surface — `OperationCoordinator.execute()`
— which delegates to the same governed pipeline. The coordinator is
**not** a governance authority: it never grants, consumes, applies or
recomputes a decision; validation, risk, approval, apply-boundary
authorization, verification and rollback all run inside the existing
governed chain unchanged.

If the same selector is already executing, the second call is rejected
as an **orchestration conflict** (fail-closed; this is not a governance
decision):

| Surface | Behavior |
|---|---|
| CLI | `Tanuq: an execution for this selector is already in flight.` + `Fail-closed: wait for the running execution to finish, then retry.` — exit `1` |
| Web `POST /api/execute` | **HTTP 409 CONFLICT** with JSON body `{"executed": false, "in_flight": true, "error": "...", "terminal": null}` |

The Web execute request additionally accepts an optional additive
`"session"` field (same semantics as CLI `--session`). All other
response codes are unchanged: `200` (normal result), `403` (missing or
invalid `X-TANUQ-Token`), `400` (malformed JSON), `413` (payload too
large). The in-flight slot is RAM-only and process-local; durable
reality remains the four hash-chained journals.

---

## Claude Code integration (PreToolUse adapter)

The first vendor-specific translation layer, built on top of the same
generic protocol above. Claude Code is NOT an authority: the adapter
is a pure input/output translation layer.

Hook registration (`.claude/settings.json`):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Edit|Write",
        "hooks": [
          {
            "type": "command",
            "command": "python -m tanuq.claude_code_adapter"
          }
        ]
      }
    ]
  }
}
```

(`Edit|Write` is the documented Claude Code matcher syntax for
"either tool exactly"; unsupported tools such as Bash never reach the
adapter through this matcher and, even if invoked directly, are
fail-closed DENY.)

Hook command interpreter: run the hook through the project's virtual environment (e.g. .venv\Scripts\python.exe -m tanuq.claude_code_adapter) or the installed `tanuq` console script. A stale global editable install that predates the tanuq package cannot import `tanuq` outside the repository root (observed friction).

Flow:

```text
Claude Code PreToolUse (Edit tool call)
↓
tanuq.claude_code_adapter (translation only)
↓
agent_adapter.propose → coordinator.execute → governed pipeline
↓
validation → governance → approval → apply → verification → evidence
↓
PreToolUse decision (always "deny": the governed channel did the work)
```

- **Input contract** (Claude Code docs): JSON on stdin with
  `tool_name: "Edit"` and `tool_input: {file_path, old_string,
  new_string}`, or `tool_name: "Write"` and `tool_input: {file_path,
  content}` (fields per the official Claude Code tools reference).
  Tool mapping (translation only):
  - `Edit` → governed `modify` (old_content = old_string)
  - `Write` → governed `create` (old_content = "" — the canonical
    no-previous-content marker; create is HIGH risk and ALWAYS
    requires human approval)
  - Write on an EXISTING file → **fail-closed DENY** (a file is never
    overwritten through Write; Edit governs modifications)
  - Anything else (Bash, other tools, missing fields, malformed JSON,
    wrong `hook_event_name`) is **fail-closed DENY**.
- **Output contract**: exit 0 + `{"hookSpecificOutput":
  {"hookEventName": "PreToolUse", "permissionDecision": "deny",
  "permissionDecisionReason": "..."}}`. The reason never contains
  patch content or secrets — only fingerprint prefixes, state and
  recommended actions.
- The adapter never returns `"allow"`: the tool call itself is
  always cancelled because the governed channel performed (or queued)
  the change. Low-risk edits are applied and verified automatically;
  HIGH/CRITICAL changes (including every Write/create) wait for human
  approval (`tanuq approve`). Once the approval is granted, retrying
  the same tool call resumes the governed execution automatically
  (the single-use, fingerprint-bound approval
  is consumed by the governed pipeline; without a valid approval the
  retry stays fail-closed DENY).

## Tanuq limits (honest)

- **Governed channel only.** Tanuq governs changes proposed through
  this protocol. An agent writing files directly (outside Tanuq) is
  not intercepted.
- **No OS sandbox, no network enforcement.**
- **Evidence is tamper-evident (detectable), not tamper-proof.**
- Verification is Python-focused (compile + pytest over the
  deterministic `related-tests-v1` profile, dummy-floor fallback);
  apply success is never treated as verification success.
- Single local operator ("human-operator"); approvals are not
  attributable to individual humans yet.

## Connected vs generic agents (P0-2.1)

Tanuq is not tied to Claude Code — or to any single agent, model or
provider. Two integration paths exist:

1. **Connected Agent (convenience/onboarding).** The Tanuq UI can
   install a vendor-specific integration for you (for example the
   Claude Code PreToolUse hook). This is configuration convenience
   only: the connect step never enters the governance chain and grants
   no authority.
2. **Generic Agent (canonical integration contract).** Any agent that
   can run a shell command integrates through the canonical proposal
   protocol — no connect step required:

   ```
   tanuq propose --stdin-json --json
   ```

Claude Code is shipped as a translation/integration adapter example
(`tanuq.claude_code_adapter`); it converts Claude's tool calls into
the same generic proposal contract every other agent uses directly.
Governance authority belongs to Tanuq's deterministic governance core
— never to an agent, model or provider.
