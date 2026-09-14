# TANUQ Project Skill — v0.1

> **Working instructions for any AI coding agent operating ON the TANUQ
> project** (developing, auditing, or reviewing it).
>
> **THIS SKILL IS NOT TANUQ RUNTIME.** It is not a governance authority,
> not an approval mechanism, not a security boundary, not a filesystem
> mutation permission, and not a replacement for the canonical protocol
> or the code. TANUQ itself is the runtime that governs AI file
> mutations; this skill only defines HOW an agent working on the TANUQ
> project should behave. Skill instructs the agent; TANUQ governance
> controls mutations.

## 1. PROJECT PURPOSE

TANUQ is an event-sourced, deterministic, human-governed file-editing
agent runtime — "AI works. You stay in control."

Every AI-proposed file change flows through a deterministic governance
chain: canonical proposal → fingerprint → risk decision → human
approval (when risky) → validation → atomic apply → real verification →
automatic rollback on failure → tamper-evident evidence.

TANUQ is NOT: an agent, a framework, a chat product, or a Claude-only
tool. The governance core is vendor-blind; vendor-specific code is
confined to translation adapters.

## 2. ARCHITECTURE OVERVIEW

```text
VENDOR tool event
  → TRANSLATION ADAPTER   (one file per vendor; translation only;
                           never returns "allow"; no filesystem writes)
  → CANONICAL PROPOSAL    {path, action, old_content, new_content, reason}
  → FINGERPRINT           (SHA-256 over proposal fields — frozen semantics)
  → GOVERNANCE / RISK     (RiskEngine — deterministic, fail-closed)
  → HUMAN APPROVAL        (single-use, fingerprint-bound, TTL; mandatory
                           for HIGH/CRITICAL)
  → EXECUTE               (OperationCoordinator — delegation-only)
  → VALIDATION            (PatchValidator — scope authority, fail-closed)
  → MUTATION              (WorkerActionPipeline → FileApplier — THE ONLY
                           workspace writer; atomic write + read-back)
  → VERIFICATION          (real workspace tests; subprocess isolation)
  → EVIDENCE              (hash-chained, append-only, tamper-evident)
```

Canonical actions today: `modify`, `create`. Nothing else (no delete,
move, shell, package, git) — adding one requires proven need + a human
design gate.

Key files (authoritative map — read them, do not trust summaries):
- `tanuq/agent_adapter.py` — canonical propose/approve/execute protocol
- `simulation/agent/worker/patch_proposal.py` — fingerprint semantics
- `simulation/security/` — risk engine, risk policy, path policy
- `simulation/agent/worker/patch_validator.py` — validation
- `simulation/agent/apply/file_applier.py` — apply/rollback primitives
- `simulation/agent/pipeline/` — apply/verify pipeline
- `tanuq/pending.py`, `tanuq/coordinator.py`, `tanuq/evidence.py`
- `tanuq/claude_code_adapter.py` — reference vendor translation adapter
- `docs/AGENT_INTEGRATION.md` — vendor integration contract
- `docs/TANUQ_PROJECT_STATE.md` — CURRENT position and handoff (read
  FIRST in every session)

## 3. FROZEN / PROTECTED BOUNDARIES

> This list is a SUMMARY. The canonical frozen-decision record is
> `docs/TANUQ_PROJECT_STATE.md` → FROZEN DECISIONS; on any conflict the
> canonical source wins.

Treat these as immutable. Reopening any of them requires evidence and
an explicit human gate:

1. `OPERATION_ID: NOT REQUIRED — FROZEN` — never add operation_id.
2. Fingerprint semantics (`patch_proposal.py`) — never change.
3. ApprovalStore semantics (single-use, TTL, fingerprint binding).
4. RiskEngine / RiskPolicy / PathPolicy behavior.
5. Canonical action set — only `modify` and `create`.
6. FAZ 7 (concurrency) and FAZ 9 (bundle identity) — closed.
7. Unified Runtime — not started; do not merge assemblies.
8. `p5/` and `agent_run.py` — separate legacy assemblies; do not touch.
9. Verification semantics: RT-2 (subprocess isolation) and R1
   (same-execution patch targets are never verification targets).
10. G1: modifying an EXISTING test module requires human approval —
    add new tests in NEW modules instead.

Protected files (any diff = stop and report): everything listed above
plus `tanuq/agent_adapter.py`, `tanuq/pending.py`, `tanuq/coordinator.py`,
`tanuq/evidence.py`, `simulation/security/*`, `simulation/agent/approval/*`.

## 4. SESSION RESYNC (do this before every task)

1. Read `docs/TANUQ_PROJECT_STATE.md` (LAST UPDATED, CURRENT PHASE,
   NEXT VALID ACTION, DAILY HANDOFF).
2. Verify reality: `git status`, `git rev-parse HEAD`, HEAD ==
   `origin/main`, recent commits, latest CI run.
3. If the recorded state contradicts the repository (unexpected diff,
   wrong HEAD, failing CI): STOP and report the contradiction — do not
   "fix forward" silently.
4. Align the task with NEXT VALID ACTION; if the task diverges,
   justify explicitly.

## 5. CODE / CHANGE DISCIPLINE

- One bounded task at a time: goal + limits + invariants → implement →
  test → drift check → report.
- Minimal scope: state upfront which files change, which tests are
  added, and what evidence will prove it.
- Tests: local full suite is `python -m pytest -q`. A release is
  FINALIZED only after the hosted CI gates (Ubuntu + Windows pytest,
  packaging gates) are GREEN.
- Touching a frozen/protected file: STOP → report → human gate.
- No speculative abstraction (registries, DSLs, plugin frameworks,
  universal interfaces) — an abstraction is justified only by an
  existing, concrete, repeated problem.
- No new authority, no new mutation writer, no second database, no
  daemons/queues.
- New vendor support = a NEW translation module (pattern:
  `tanuq/claude_code_adapter.py`) + NEW test module + docs update;
  canonical core diff should be zero.
- Never invent a vendor payload schema; use official vendor
  documentation or real runtime evidence, and label which one.

## 6. STOP RULES

Stop coding and report (with a human gate) when any of these appears:
1. Missing evidence (unknown payload/protocol/state).
2. A frozen/protected file must change.
3. New authority, mutation writer, or abstraction seems necessary.
4. Fingerprint/approval/verification semantics must change.
5. Unexpected repository state or PROJECT_STATE contradiction.
6. Test failure you cannot explain, or an unverifiable result.
7. The task conflicts with NEXT VALID ACTION without justification.

## 7. EVIDENCE DISCIPLINE

Label every claim; never present inference as observation:
- CONFIRMED — observed with tools this session (cite file/line/output)
- VENDOR DOCUMENTED — official vendor documentation (runtime not yet
  observed; say so)
- INFERRED — logical derivation from code flow
- UNKNOWN — not known; do not guess
- BLOCKED — external dependency (e.g. API credit); report as blocked,
  do not fake progress
- RECORDED — NOT RE-RUN — prior session result, not re-verified here

Fabricated payloads, outputs, or results are a hard violation.

## 8. VENDOR ADAPTER RULES

- Translation layer only: parse vendor event → canonical proposal →
  `agent_adapter.propose` → `OperationCoordinator.execute`. The result
  surfaced to the vendor is always "deny" (the governed channel did
  the work).
- An adapter must never: return "allow", grant approvals, decide risk,
  produce fingerprints, write files, or bypass governance.
- Unsupported / missing / malformed input → fail-closed DENY.
- Regression-guard existing vendor behavior on every adapter change.

## 9. HARD NO

- Never commit: `child_*.dmp` (real secrets), `_dbg_*`, `_diag*`,
  `_run_obs.py`, `_verify_postfix*.py`, `dist/`, `t`, `request.json`.
- Never start: operation_id, bundle identity, FAZ 7/9, Unified
  Runtime, generic normalizer, plugin framework, provider registry.
- Never add queues/daemons/second databases.
- Never treat VERIFIED as APPROVED or as a governance decision.
- Never rewrite governance/approval/fingerprint/journal semantics.
- Never give a translation adapter authority or write access.
- Never use this skill as if it were runtime authority — it instructs,
  it does not control.

## 10. REPORT FORMAT (end of every meaningful task)

RESYNC / FILES CHANGED / IMPLEMENTATION / SECURITY AUDIT / TEST RESULTS
(with counts) / DOGFOOD (if any) / REGRESSION / GIT STATUS / CI /
REMAINING RISKS / UNKNOWN / FROZEN DECISIONS: UNCHANGED / COMMIT /
PUSH / NEXT BEST ACTION (exactly one) / HUMAN GATE (if any).

## 11. BDP v1.5 (append to every meaningful report)

- ASSUMPTIONS: list explicitly.
- EVIDENCE: ARAÇ (tools) / MANTIK (logic) / KULLANICI (user) / HESAP
  (records) / EĞİTİM (prior knowledge) — tag each basis.
- CONFIDENCE: [YÜKSEK / ORTA / DÜŞÜK] — per claim group, not global.
- MODE: UYGULAYICI (implementer) / PLANLAYICI (planner) / TEMİZLİKÇİ
  (cleaner).

## 12. READ-ONLY vs MUTATING TANUQ API (inspection discipline)

Real finding: during a diagnosis session, `agent_adapter.approve()` was
called under a read-only umbrella and produced a real TYPE_GRANT in the
approval ledger. Inspection tools MUST be read-only.

READ-ONLY (safe for inspection/diagnosis):
- `load_pending` — pending store read
- `verify` / `tanuq verify` — chain/anchor validation
- `status` / `tanuq status` — protection summary
- `operations()` — operation projection
- `lineage()` — fingerprint-joined lifecycle view
- `incidents()` — detect-only incident projection
- `export()` — audit bundle (read-only)
- `chain_status()` — chain/anchor status
- `tanuq history` — read-only apply-outcome lifecycle

MUTATING (state-changing; only inside an explicitly approved task):
- `propose()` / `tanuq propose` — writes pending + events
- `approve()` — writes approval ledger TYPE_GRANT (a real
  authorization artifact — never a diagnostic step)
- `execute()` / `tanuq execute` — applies file mutations
- `remove_pending()` — deletes pending records
- `ApprovalStore.revoke()` — revokes an approval

RULE: during inspection/diagnosis use ONLY the READ-ONLY set. MUTATING
API calls change state and belong in a separately approved task scope.

## 13. CANONICAL SOURCES


If this skill ever contradicts these, the canonical source wins:
`docs/TANUQ_PROJECT_STATE.md` (current position), `docs/SECURITY_MODEL.md`,
`docs/AGENT_INTEGRATION.md`, the code itself. Report the contradiction.
