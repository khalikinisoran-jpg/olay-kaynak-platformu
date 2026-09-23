# TANUQ — Sol Adversarial Review Consolidation 01
# (A1-A4 CLI/API authority surface + Q1-Q2 verification/TTL)

> STATUS: research record only — consolidates the independent
> adversarial review by GPT-6 Sol with the GLM source-based audit and
> live disposable-workspace verification performed in this session.
> **NO PRODUCTION CODE CHANGE** (tanuq/, simulation/, tests/ diff = 0),
> NO commit/push, NO new tests. Results are recorded as verified; no
> finding was softened or re-interpreted beyond the evidence.

Verification basis: every finding below was re-verified against real
source and, where marked LIVE, reproduced in a disposable scratch
workspace (`%TEMP%\tanuq-sol-audit`) — never the production repo.

---

## 1. A1 — CLI SELF-APPROVAL

**CLASSIFICATION: DEPLOYMENT-DEPENDENT.** (NOT a confirmed core
governance gap — see CORE GOVERNANCE below.)

- SOURCE (mechanism confirmed): `tanuq/agent_adapter.py:248-289`,
  `tanuq/cli.py:161-183`. `approve()` calls
  `ApprovalStore.grant(..., authorizer="human-operator")`. The
  `authorizer` is a static string; there is NO real operator identity
  or authentication. LIVE: a HIGH proposal in the scratch workspace
  was approved with a single `tanuq approve` call
  (approval_id=c331c905, risk=HIGH). Attack path: propose → approve →
  execute.
- CASE A (agent produces proposal JSON/hook only): self-approval
  bypass NOT possible — the canonical stdin-json channel projects to
  the five proposal fields; no approve path exists there.
- CASE B (agent can run shell/CLI in the same environment): approve +
  execute ARE possible — full self-service loop.
- CASE C (direct Python import/API access): `ApprovalStore.grant` is
  directly callable; code execution is already outside every
  governance boundary.
- Current deployment documentation states the honest limit: "No OS
  sandbox" (cli.py:97-100). In the existing single-user/local
  deployment model the agent and the operator share one trust domain,
  so this is recorded as a REAL security concern for multi-user /
  untrusted-shell deployments only — not as a core governance bypass.

## 2. A2 — EXPORT ARBITRARY WRITE

**CLASSIFICATION: CONFIRMED / OPERATOR-SURFACE HARDENING.**

- SOURCE: `tanuq/cli.py:703-706`. `--out` creates the parent directory
  (`mkdir(parents=True, exist_ok=True)`) and `write_text`s with NO
  scope/PathPolicy/traversal validation. The command self-describes as
  "Read-only secret-safe evidence bundle" (cli.py:850) — the `--out`
  write primitive contradicts that label.
- LIVE: export to an absolute path OUTSIDE the workspace scope (a
  directory that did not exist) succeeded — directory created, file
  written.
- Agent access: CASE B only. CASE A has no path to this command.
- Impact: out-of-scope file write / tampering / DoS with the exported
  (fixed, evidence-derived) JSON content — not arbitrary content
  generation.
- Production fix: NOT applied (owner decision pending).

## 3. A3 — INIT FORCE SCOPE WIDENING

**CLASSIFICATION: CONFIRMED / OPERATOR-SURFACE HARDENING.**

- SOURCE: `tanuq/cli.py:52-84`, `tanuq/config.py:284-286`.
  `--force --yes` without `--allowed-path` passes `allowed=None` →
  default scope = whole workspace → a previously NARROWED scope is
  widened back. Evidence and approvals are kept across `--force`.
- LIVE: narrowed scope (`...\tanuq-sol-audit\sub`) →
  `tanuq init --force --yes` → scope widened to the whole workspace
  (verified via config.json before/after).
- Attack: widen scope, then an out-of-scope LOW proposal auto-applies.
- Agent access: CASE B only; `init` is operator bootstrap tooling and
  is not part of the agent proposal/execute channel.
- Impact: persistence of a narrowed scope depends on operator
  discipline.
- Production fix: NOT applied (owner decision pending).

## 4. A4 — /api/pending DISCLOSURE

**CLASSIFICATION: CONFIRMED / LOCAL DISCLOSURE / OPERATOR-SURFACE
HARDENING.**

- SOURCE: `tanuq/web.py:150` — GET endpoints perform NO token check
  (`_check_token` guards POST only, web.py:269-271). `/api/pending`
  (web.py:208-210) returns `_pending_view()` (web.py:676-711): path,
  reason, fingerprint and `diff.old_preview`/`diff.new_preview`
  (first 2000 chars of proposal content). Server binds 127.0.0.1 only
  (web.py:847,883) — no remote/public exposure.
- LIVE: UI started; `GET /api/pending` WITHOUT any token returned
  HTTP 200 including `diff.new_preview` of a pending HIGH proposal
  ("token = FAKE-VALUE-FOR-AUDIT"). Server stopped afterwards.
- Impact: another local process/user on the same machine can read
  pending proposal content — including proposals from OTHER
  sessions/sources. The agent already knows its own proposals; the
  exposure is cross-session content disclosure.
- Production fix: NOT applied (owner decision pending).

## 5. Q1 — APPROVAL TTL

**CLASSIFICATION: CONFIRMED / DEFENSE-IN-DEPTH HARDENING.**

- SOURCE: `approval.py:176-205` — `expires_at=None` → `""`; docstring:
  "``None`` means the approval never expires" (line 183);
  `is_expired` treats empty as never-expiring (211-216).
  `ApprovalStore.grant` defaults `expires_at=None` (approval_store.py:155).
  Neither `agent_adapter.approve` (268-275) nor the UI `_approve`
  (web.py:714-716) passes `expires_at` — yet the CLI prints
  "TTL=3600s" (cli.py:179) and `what_this_authorizes` says
  "expires 3600s after granting" (web.py:701).
- LIVE: ledger grant record shows `expires_at=''`.
- RESULT: fingerprint binding and single-use ARE real; the advertised
  TTL is NOT enforced — an unconsumed approval stays valid
  indefinitely. This is a defense-in-depth hardening item and a
  broken advertised contract, NOT a proposal-authority bypass.
- Production fix: NOT applied (owner decision pending).

## 6. Q2 — VERIFIER SIDE EFFECT

**CLASSIFICATION: PARTIAL / RESIDUAL VERIFIER TRUST BOUNDARY.**
(This is NOT a confirmed agent bypass.)

- SOURCE: `verification_executor.py:34-43` — RT-2 mitigations:
  temp cwd, Tanuq-owned pytest `-c` config, `--confcutdir`,
  `PYTEST_ADDOPTS`/`PYTEST_PLUGINS` scrub. `verification_profile.py:
  105-135` — RT-1 R1: a same-execution patch target test module never
  verifies itself (dummy floor fallback). `risk_engine.py:536-558` —
  G1: modifying an EXISTING test module is HIGH; `create` is HIGH.
- RESULT: agent-controlled NEW code reaches verification only AFTER
  human approval; steering vectors (conftest/addopts/env) are scrubbed.
- RESIDUAL (recorded, by-design): verification executes workspace test
  code in a subprocess; PRE-EXISTING test code runs with the operator
  user's privileges and can mutate outside the governed scope —
  the documented "No OS sandbox" honest limit. No OS sandboxing of the
  verifier exists today.

## 7. CORE GOVERNANCE vs NEW AUTHORITY SURFACE

**CORE GOVERNANCE:** the chain
proposal → deterministic risk → policy → approval binding → apply →
verification → evidence was re-examined across LUNA-07..12 and again
in this review: **no core authority bypass was found.** Fingerprints
bind every agent-controlled field; approvals are single-use and
store-backed; the apply boundary recomputes risk from the patch; the
apply boundary and pipeline share one GovernanceEvaluator.

**NEW AUTHORITY SURFACE:** the TANUQ CLI, the local UI/API and the
operator commands (`approve`, `export --out`, `init --force`, the
unauthenticated GET endpoints) form a SEPARATE authority surface that
the untrusted-proposer analyses do not cover. All confirmed findings
(A2/A3/A4/Q1) live on this operator surface, not in the governance
core. Their severity is bounded by the deployment boundary: an agent
that can only produce proposals (CASE A) cannot reach any of them.

## 8. OWNER DECISION NEEDED

No implementation decision has been made on the following:

1. Should the advertised 3600s approval TTL actually be enforced
   (`expires_at=APPROVAL_TTL_SECONDS` at grant time)?
2. Should `GET /api/pending` require the local access token (and/or
   drop diff previews)?
3. Should `export --out` be scope-bound, or should its read-only
   semantics be restated?
4. Should `init --force --yes` keep the scope-widening behavior, or
   require explicit operator confirmation of the new scope?
5. Should CLI approval require a real operator identity /
   authentication (multi-user deployments)?
6. Is an OS sandbox for the verifier needed in the future (pre-existing
   test-code trust boundary)?

## 9. DISPOSITION

- A1 = DEPLOYMENT-DEPENDENT (mechanism real; not a core governance
  gap in the current single-user/local deployment).
- A2/A3/A4 = confirmed implementation issues / operator-surface
  hardening (LIVE-verified).
- Q1 = confirmed defense-in-depth hardening (advertised TTL not
  enforced).
- Q2 = PARTIAL / residual verifier trust boundary (pre-existing test
  code; by-design, documented).
- **NO PRODUCTION CODE CHANGE.** No production fix has been applied;
  every item above awaits the owner decisions in §8.
