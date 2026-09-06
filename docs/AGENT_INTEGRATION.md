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

---

## Tanuq limits (honest)

- **Governed channel only.** Tanuq governs changes proposed through
  this protocol. An agent writing files directly (outside Tanuq) is
  not intercepted.
- **No OS sandbox, no network enforcement.**
- **Evidence is tamper-evident (detectable), not tamper-proof.**
- Verification is Python-focused (compile + pytest); apply success is
  never treated as verification success.
- Single local operator ("human-operator"); approvals are not
  attributable to individual humans yet.
