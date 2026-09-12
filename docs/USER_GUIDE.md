# Tanuq — User Guide

> **AI works. You stay in control.**

Tanuq is a local agent governance runtime. It checks every file change
your AI coding agent proposes, asks for your approval when a change is
risky, rolls back changes that break verification, and keeps
tamper-evident evidence of everything that happened.

Full value statement:

> Tanuq governs file changes proposed by AI coding agents with
> deterministic security policies, binds risky changes to explicit
> human approval, rolls back failed changes automatically, and records
> every operation as verifiable evidence.

---

## Quick start (first 5 minutes)

Requirements: Windows 10/11 or Linux, Python 3.12+.

```bash
pip install -e .
tanuq init
```

`tanuq init` walks you through:

1. **Workspace** — the project folder you want to protect (default:
   current directory).
2. **Allowed paths** — which folders inside the workspace may be
   modified (default: the whole workspace). You can only *narrow* the
   scope, never widen it beyond the workspace.
3. **Verification depth** — `compile` or `compile+tests` (default:
   compile + run tests).

Tanuq then:

- creates its data under `<workspace>/.tanuq/` (config, evidence
  journals, event store),
- generates an anchor key under `~/.tanuq/keys/` (outside any
  repository) and activates **anchored, tamper-evident evidence**,
- starts in **governed mode**: HIGH/CRITICAL risk changes always
  require your approval, UNKNOWN is always denied.

Check protection:

```bash
tanuq status
```

---

## Daily usage

### 1. A change is proposed

Your AI agent (or you) submits a proposal:

```bash
# human mode
tanuq propose --file app.py --old-content "..." --new-content "..."

# agent hook mode: one JSON proposal object (or an array) on stdin
echo '{"path": "app.py", "old_content": "...", "new_content": "...", "reason": "fix typo"}' \
  | tanuq propose --stdin-json --json
```

> **Note (modify):** `old_content` must be the ENTIRE current
> file content, not a snippet or region. If it does not match, Tanuq warns
> you at propose time and denies the change at execute time as stale
> — resubmit with the exact current file content.

Tanuq answers in plain language:

- `Risk: LOW — safe to apply automatically`
- `Risk: MEDIUM/HIGH — approval required`
- `DENIED — outside the protected workspace`

The proposal is stored with a **fingerprint** (a SHA-256 summary of the
exact change). Approval binds to that fingerprint.

### 2. Approve (only for risky changes)

```bash
tanuq approve            # approve all pending risky proposals
tanuq approve --fingerprint 3fb6e981   # approve one specific proposal
```

An approval is **single-use** (one approval = one execution), expires
after 1 hour, and is valid only for the exact approved content.

### 3. Execute

```bash
tanuq execute            # oldest pending proposal
tanuq execute --all      # whole queue (fail-fast)
tanuq execute --fingerprint 3fb6e981
```

Tanuq applies the change atomically, then **verifies** it (Python
compile check + tests, depending on depth). Apply success is never
treated as verification success:

- verified → `VERIFIED`
- verification failed → the change is **automatically rolled back** →
  `ROLLED_BACK`
- out of scope / policy → `DENIED`

If you run `tanuq execute` while another execution for the same
selection is still running, Tanuq refuses the second run (fail-closed):
`an execution for this selector is already in flight` — wait for the
running execution to finish, then retry. In the Web UI the equivalent
request returns **HTTP 409 CONFLICT**. This is an orchestration
conflict only; it is never a governance or authorization decision.

### 4. Inspect history and evidence

```bash
tanuq history            # lifecycle of every apply intent
tanuq verify             # Evidence chain: VALID/INVALID, Anchor: ACTIVE
tanuq status             # protection summary
```

`tanuq verify` re-computes the whole hash chain and checks it against
the keyed anchor. If anyone edited or deleted evidence, this reports
`INVALID` / `FAILED`.

---

## The Tanuq UI

```bash
tanuq ui                 # serves http://127.0.0.1:8770 (this workspace)
```

The UI is a view layer only — it never decides anything and never
writes files; every action goes through the same governed runtime as
the CLI. Screens:

| Screen | What you see | What you can do |
|---|---|---|
| Dashboard | Workspace, governed mode (always ON), anchor status, pending count, recent verified changes, blocked count, last result | Navigate, refresh |
| Pending Approvals | Target file, action, risk, **diff**, fingerprint, creation time, TTL, and an explicit "what does this approval authorize" statement | Approve / Reject |
| Activity | Per-operation lifecycle from the apply journal: `intent → apply_started → applied → verified` etc., terminal state | Read |
| Evidence | Event chain (sequence, type, fingerprint, hash), chain VALID/INVALID, anchor ACTIVE/FAILED | Verify now |
| Blocked Actions | Denied proposals with target, risk and the exact deny reason (from recorded evidence) | Read |
| Status | Protection summary with the honest limits | Read |

**Token:** every state-changing action in the UI requires your local
device token (created by `tanuq init`). Run `tanuq token` to see it
and paste it into the UI once; it is stored only in your browser and
sent as `X-TANUQ-Token`. Requests without a valid token are rejected
(fail-closed 403). The token is an access control for YOUR browser —
it is never treated as an approval; governance decisions always come
from the deterministic runtime.

The UI states the honest limits on every page: no OS sandbox, no
network enforcement, Tanuq only governs changes proposed through
Tanuq, and evidence is tamper-evident (changes are detectable), not
tamper-proof.

---

## How decisions are made

For every proposal, in order:

1. **Scope check** — is the target file inside the allowed paths?
   (path traversal and symlink escapes are rejected)
2. **Deterministic risk classification** — the system measures risk
   from the path, action, change size and content (secrets, credential
   patterns, production config, destructive actions). The AI's own risk
   claim is never trusted; it can only make the classification *stricter*.
3. **Policy** — UNKNOWN → denied; HIGH/CRITICAL → your approval
   required; LOW/MEDIUM → auto-apply with verification.
4. **Single-use approval** (when required) — bound to the exact
   fingerprint, consumed on use.
5. **Atomic apply** — the write is atomic (never a half-written file)
   and the result is read back and checked.
6. **Verification** — independent of apply. Failure triggers rollback.
7. **Evidence** — every step is appended to hash-chained, secret-safe
   journals (events, approvals, apply outcomes) anchored with an HMAC
   key.

These rules are built into Tanuq. There is no configuration option
(and no AI instruction) that can relax them.

---

## What Tanuq does NOT do (honest limits)

- **No OS sandbox.** Tanuq governs changes proposed *through* Tanuq.
  If an agent writes to the filesystem directly (outside Tanuq), this
  governance chain does not intercept it.
- **No network control.** Tanuq does not restrict or monitor your
  agent's network access. External network providers are not
  implemented.
- **Python-focused verification.** Verification runs a Python compile
  check and pytest. Projects without Python tests still work; the
  verification value is then mostly the compile/consistency check.
- **Evidence is tamper-evident, not tamper-proof.** Anyone with your
  user account (and the key under `~/.tanuq/keys/`) could rewrite
  data AND the key. Tanuq detects tampering by an agent or a process
  without the key; it cannot stop the machine's owner.
- **Key loss.** If you delete the anchor key, previously anchored
  evidence can no longer be verified (fail-closed). Back the key up if
  the evidence matters to you.
- **Local, single-user.** One workspace, one operator
  ("human-operator"). Remote approval and multi-user identity are not
  implemented.

## Which agents can connect?

Any agent that can run a shell command can submit proposals through
the generic CLI hook (`tanuq propose --stdin-json`) and read results
(`--json`). Tanuq does not currently claim native support for any
specific commercial agent; integrations are verified per agent, not
assumed.

## Troubleshooting

| Symptom | Meaning | What to do |
|---|---|---|
| `DENIED — outside the protected workspace` | Target path is not inside the allowed paths | Move the change into scope or re-`tanuq init` with a narrower/wider *inner* scope |
| `Approval missing or already used` | Single-use approval was consumed or expired | `tanuq approve` again (a fresh approval is required for every risky change) |
| `ROLLED_BACK` | Verification failed after apply | Nothing to fix — the file was restored; check the failure reason printed by `tanuq execute` |
| `Evidence chain: INVALID` | Journals were edited or corrupted | Stop trusting history; inspect `.tanuq/data/` and restore from backup |
| `Anchor key file is missing` | Key under `~/.tanuq/keys/` was deleted | Tanuq refuses to run fail-closed; restore the key backup or re-init (old evidence stays unverifiable) |
