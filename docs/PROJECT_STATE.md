# PROJECT_STATE.md

# Event-Sourced AI Runtime

Canonical project state. Source of truth for what actually exists.
Evidence hierarchy: Git history > source code behavior > automated test
results > documentation.

---

## Project Information

| Field | Value | Classification |
|-------|-------|----------------|
| Project Name | Event-Sourced AI Runtime | VERIFIED (docs) |
| Status | Active Development | VERIFIED (git activity) |
| Last Updated | 2026-08-21 | VERIFIED |
| Active Branch | `worker-action-pipeline` | VERIFIED (`git branch --show-current`) |
| Branch HEAD | `24c72d0` (`24c72d01690a6a1645317cb2b52c26c532731587`, "fix(edge-case): clamp provenance trust levels in from_dict") — clean, local == remote | VERIFIED (`git rev-parse HEAD`, `git status`) |
| Remote | `origin` = https://github.com/khalikinisoran-jpg/olay-kaynak-platformu.git | VERIFIED (`git remote -v`) |
| Branch relationship | `worker-action-pipeline` is 30 commits ahead of `main`; `main` has 0 commits not in `worker-action-pipeline` | VERIFIED (`git log main..HEAD`, `git log HEAD..main`) |
| Latest release tag | v0.5.0 (2026-08-07, "Memory Recall Runtime") — no tag after v0.5.0 for this branch | VERIFIED (`git tag`) |
| Tags | v0.1.0-alpha, v0.3.0, v0.4.0, v0.5.0 | VERIFIED |
| Python | 3.12 (pyc artifacts indicate cpython-312); pytest 9.1.1 in `.venv` — suite **`986 collected / 974 passed / 12 skipped / 0 failures`** | VERIFIED (`.venv\Scripts\python.exe -m pytest --version`, MISSION N.55) |

---

# Purpose

Build an event-sourced AI runtime in which every meaningful AI action
becomes an immutable, hash-chained event, so that AI-driven decisions can
be replayed, recovered, verified, audited and constrained by deterministic
system controls.

Product claim (not yet externally validated): "trustworthy AI through
Event Sourcing, Replay, and Verification." See docs/PRODUCT_POSITIONING.md.

---

# Current Product Definition

What is actually implemented and verifiable today:

- A CLI runtime (`agent_run.py`) that routes user input through a Planner
  to a StrategyDispatcher with five executors: `calculator`, `memory_store`,
  `memory_recall`, `llm`, `worker`.
- A proposal-only default path: a `worker:` prefixed prompt makes the
  Worker read in-scope files and produce patch proposals, but the default
  runtime never applies them (`simulation/agent/agent.py:46`, tests
  `tests/worker_runtime_test.py::test_default_agent_runtime_is_proposal_only_no_apply_no_verify`).
- An opt-in mutation path: `python agent_run.py --recovery` wires
  `build_recovery_agent()` which enables apply + verification + bounded
  recovery for in-scope files. Since MISSION-018B the authorization
  boundary stays ACTIVE: the apply boundary recomputes risk and DENIES
  every HIGH/CRITICAL/UNKNOWN apply without a store-verified approval, and
  `--recovery` wires the risk gate + approval store + ledger so
  HIGH/CRITICAL/UNKNOWN fail closed unless a pre-granted ledger approval
  exists (no interactive prompt; that is `--governed`'s role). LOW/MEDIUM
  auto-apply with rollback on verification failure and bounded retry.
- A **governed apply path**: `python agent_run.py --governed` adds the
  deterministic risk gate and a store-backed, single-use human-approval
  boundary with a durable approval ledger (MISSION-016). HIGH/CRITICAL fail
  closed without a valid approval; LOW/MEDIUM auto-apply with rollback on
  verification failure.
- **Rollback on verification failure** (MISSION-016): a patch whose
  verification fails is rolled back to its exact pre-apply content before
  any recovery retry; a rollback failure is terminal (`FAILURE_ROLLBACK`),
  and rollback outcomes are recorded as `WorkerRollbackSucceeded` /
  `WorkerRollbackFailed` events.
- **Durable approval state** (MISSION-016): `ApprovalLedger` persists
  grant/consume/apply transitions; consumed approvals stay consumed after a
  restart; a corrupted ledger fails closed.
- A real-LLM code analyzer (OpenRouter, DeepSeek) behind a hardened
  provider layer; only proposal generation, never file mutation
  (MISSION-003, gated `live_llm` tests). **Secret files are skipped and
  secret-like values are redacted before content reaches the analyzer**
  (MISSION-016); providers are created lazily so non-LLM strategies run
  without an API key.
- A risk/verification pipeline (RiskEngine/RiskPolicy/RiskLevel) that is
  deterministic, tested (MISSION-011: 83 tests; MISSION-018A: fail-closed
  content classification + risk-regression corpus) and correctly integrated
  as an explicit opt-in gate at the pipeline and assembly level; it is NOT
  active in the default runtime (see Known Limitations). Risk path matching
  was refined (MISSION-016) to use token boundaries for `auth`/`token`/
  `secret` and a deterministic regression corpus was added. MISSION-018A
  made content classification fail-closed: `not detected` is never treated
  as `safe`. Content is classified as SAFE (plain; may auto-apply as
  LOW/MEDIUM), SUSPICIOUS (credential-like material -> HIGH, human approval
  required) or OPAQUE (control characters -> UNKNOWN -> DENY). The audited
  evasion classes (JSON/bare-token/base64/URL/shell/env/auth-header
  credentials; `.bak`/`.creds`/`prod.yaml`/`secrets/*` paths) are now
  regression-locked (corpus A37-A50).
- A human approval boundary (MISSION-012): fingerprint-bound, single-use,
  evidence-recorded `Approval` / `ApprovalStore`; HIGH/CRITICAL fail closed
  without a valid approval; granted approvals are recorded as
  `WorkerHumanApprovalGranted` events. Also an explicit opt-in, never in
  the default runtime.
- **An interactive CLI human-approval interface** (MISSION-017):
  `ConsoleApprovalGateway` + `approval_console.py` renders a HIGH/CRITICAL
  request (patch fingerprint, path, action, risk level + context, attempt,
  expiry, authorizer, evidence reference) and routes an explicit human
  approve/deny into `ApprovalStore.grant`. It is wired into
  `agent_run.py --governed` and the pipeline consults it only when no valid
  stored approval exists; the grant still flows through `find_valid` +
  `authorize_apply`, so the store/apply boundary remains the authority and
  agent-controlled approval metadata stays non-authoritative. Tested in
  `tests/approval_console_test.py` (23 tests) and corpus A31-A36.
- A hardened authorization boundary (MISSION-014): the apply boundary
  requires a typed `ControllerDecision` (`approved is True` + exact
  fingerprint) and, for HIGH/CRITICAL/UNKNOWN applies, a store-verified,
  single-use approval binding consumed at the apply boundary. Risk is
  recomputed deterministically at the boundary, so forged decisions,
  agent-claimed approval ids, replayed approvals, evidence-only metadata
  and approval objects bound to a different patch cannot reach apply.

---

# Current Architecture

Described in detail in docs/ARCHITECTURE.md. Summary of what exists in code:

1. Core event sourcing: `Event`, `State`, `Reducer`, `Kernel`
   (simulation/core/).
2. Persistence: `EventStore` (append-only JSONL + SHA-256 hash chain),
   `SnapshotStore`, `SnapshotManager`, `RecoveryEngine` (snapshot + replay
   + hash-integrity) (simulation/persistence/, simulation/recovery/,
   simulation/replay/, simulation/security/hash_chain.py).
3. Runtime orchestration: `Planner`, `LoopEngine`, `DecisionTrace`,
   `StrategyDispatcher`, `ExecutorRegistry` + executors (calculator,
   memory_store, memory_recall, llm, worker).
4. Memory: `MemoryService`, `MemoryEvents`, `MemoryStored` event,
   automatic store / recall executors.
5. Tools: `BaseTool`, `Registry`, `ToolExecutor`, `Calculator`.
6. Worker action pipeline (opt-in): `WorkerAgent` -> `PatchValidator` ->
   `Controller` -> `ApplyExecutor`/`FileApplier` -> `VerificationExecutor`
   -> optional `BoundedRecoveryEngine`, recorded by `WorkerEvidenceRecorder`
   (simulation/agent/pipeline/, simulation/agent/recovery/,
   simulation/agent/evidence/).
7. Risk engine (VERIFIED, MISSION-011): `RiskEngine`, `RiskPolicy`,
   `RiskLevel` (simulation/security/risk_*.py). Deterministic system-derived
   classification; advisory LLM risk can only raise; policy maps UNKNOWN->
   DENY, HIGH/CRITICAL->human approval, LOW/MEDIUM->auto. Integrated as an
   explicit opt-in gate in `WorkerActionPipeline` and `build_recovery_agent`.
8. Human approval boundary (VERIFIED, MISSION-012): `Approval`,
   `ApprovalStore` (simulation/agent/approval/). Single-use,
   fingerprint/path/action/risk/attempt/expiry-bound; pipeline validates
   the returned approval itself (`_approval_is_valid`); grants recorded as
   `WorkerHumanApprovalGranted` evidence events.
9. Security: `PathPolicy` (canonical containment, traversal/symlink/junction
   rejection), `HashVerifier`, fail-closed validation contracts.

---

# Security Boundary

Detailed in docs/SECURITY_MODEL.md. Current boundary (all VERIFIED except
where noted):

- Path scope enforced by `PathPolicy.check_scope` (canonical resolve +
  normcase + containment) and re-checked at write time in `FileApplier`
  through `PathPolicy.resolve_target`.
- Patch validation requires exact full-file `old_content` match, in-scope
  target, `modify` action only, non-empty change.
- Apply requires a `ControllerDecision` with `approved is True` and a
  fingerprint that exactly matches the patch. When the risk gate is
  enabled, the apply boundary is store-backed: HIGH/CRITICAL/UNKNOWN
  applies additionally require a store-verified, single-use approval
  binding (approval identity + exact patch object), so forged decisions,
  fake objects, agent-claimed approval ids, replayed/expired approvals,
  evidence-only metadata and approval-to-apply substitution fail closed
  (MISSION-014, ApplyAuthorization).
- Post-write read-back: written bytes are compared to approved
  `new_content`; mismatch triggers bounded restore + FAIL.
- Verification is deterministic (compileall + pytest via non-shell arg
  list); apply success is never verification success.
- Retry is bounded (hard cap 3; no recursion; duplicate fingerprints stop).
- Default runtime is proposal-only; apply only via explicit assembly.
- Risk gate is an explicit opt-in (requires both `risk_engine` and
  `risk_policy` on `WorkerActionPipeline` or `build_recovery_agent`). When
  active: RiskEngine -> RiskPolicy -> Controller -> ApplyVerifyPipeline,
  UNKNOWN/DENY stops before apply, HIGH/CRITICAL require a valid human
  approval from the `ApprovalStore` (fingerprint/path/action/risk/attempt/
  expiry-bound, single-use, fail-closed on missing/malformed/expired/
  wrong/replayed approval) and the apply boundary itself re-verifies the
  consumed approval binding (MISSION-014). **VERIFIED** — tests/risk_*.py
  (MISSION-011), tests/approval_boundary_test.py (48 tests) + corpus
  A01-A20 (MISSION-012/013/014).

---

# Verification Model

- Deterministic verification layers: `PatchValidator` (scope/staleness),
  `Controller` (typed `ValidationResult`, `valid is True` only), `ApplyVerifyPipeline`
  (apply must pass before verification runs), `VerificationExecutor`
  (`python -m compileall -q <paths>` then `python -m pytest -q <targets>`,
  PASS/FAIL with preserved stdout/stderr/exit code/evidence).
- Verification depth switch (`compile` vs `compile+tests`) added in MISSION-011
  (`apply_verify_pipeline.py:31`). Both paths are now tested (MISSION-011):
  `verification_depth="compile"` calls `verify_python_compile` only;
  default/`compile+tests` calls `verify`. The policy currently selects
  `compile+tests` for every non-deny level.
- Live LLM behavior is only covered by opt-in gated tests
  (`RUN_LIVE_LLM=1 python -m pytest -m live_llm tests/llm_provider_integration_test.py -q`).

---

# Recovery Model

Two distinct recovery mechanisms exist:

1. **Persistence recovery** (`simulation/recovery/recovery_engine.py`):
   verifies hash chain, loads snapshot if present, replays remaining
   events. Wired into `Kernel.__init__` (every Kernel start).
2. **Bounded verification recovery** (`simulation/agent/recovery/bounded_recovery_engine.py`):
   retries a verification FAIL up to a hard cap of 3 attempts with
   duplicate-fingerprint suppression and append-only attempt history.
   Active only when the agent is assembled via `build_recovery_agent()`
   or `agent_run.py --recovery`. **Authorization (MISSION-018B):** each
   retry is an independent PatchProposal that flows through risk
   classification and the store-backed approval/apply boundary; an older
   attempt's approval never authorizes a newer patch, and the retry budget
   never substitutes for human authorization.

Recovery is NOT active by default in the shipped runtime
(`agent_run.py` uses proposal-only `Agent(kernel)` unless `--recovery`).

---

# Evidence / Audit Model

- Every `kernel.dispatch()` writes a normal Event into the append-only
  EventStore with `previous_hash`/`current_hash` (SHA-256 chain);
  `HashVerifier.verify` recomputes from GENESIS.
- `WorkerEvidenceRecorder` (MISSION-004) records worker lifecycle event
  types plus DecisionTrace steps. Payloads are secret-safe: only patch
  fingerprints (SHA-256) and status/exit-code/failure-reason, never
  old/new content, stdout/stderr, or API keys.
- Human approval grants (MISSION-012) are recorded as
  `WorkerHumanApprovalGranted` events through the same Kernel/event store;
  payloads carry the approval binding fields (fingerprint, path, action,
  risk level, attempt, authorizer, timestamps) and never patch content.
- DecisionTrace is in-memory only; the hash-chained event log is the
  durable evidence (documented design decision, ADR-001 / MISSION-004).

---

# Test State

Authoritative run on 2026-08-21 (MISSION N.55 foundation, HEAD `24c72d0`):

```
.venv\Scripts\python.exe -m pytest -q
974 passed, 12 skipped in 78.55s (986 collected)
```

- 12 skipped: 3 opt-in `live_llm` integration tests (never run in the
  normal suite) + 9 symlink-dependent tests that skip where the OS denies
  symlink creation (junction variants pass on this Windows environment;
  the symlink records run in CI on ubuntu-latest).
- MISSION N.55 reproduced the baseline **`986 collected / 974 passed / 12 skipped / 0 failures`** via `python -m pytest -q` (FULL method). Previous close-outs (902/881) are superseded.
- Gated live run (real provider): `RUN_LIVE_LLM=1 python -m pytest -m
  live_llm tests/live_llm_e2e_test.py -q` → opt-in; skipped in normal suite.

Coverage by module (test counts, VERIFIED by `pytest --collect-only` on
2026-08-16):

| Test module | Count |
|-------------|-------|
| tests/approval_boundary_test.py | 48 |
| tests/structured_analysis_test.py | 41 |
| tests/security/adversarial_corpus_test.py | 80 (A01-A75 + summary) |
| tests/recovery_engine_test.py | 33 |
| tests/worker_contract_test.py | 31 |
| tests/security/path_security_test.py | 31 |
| tests/risk_engine_test.py | 30 |
| tests/approval_console_test.py | 23 |
| tests/risk_level_test.py | 20 |
| tests/risk_policy_test.py | 18 |
| tests/security/worker_read_scope_test.py | 16 |
| tests/verification_executor_test.py | 15 |
| tests/risk_pipeline_test.py | 15 |
| tests/controller_decision_test.py | 13 |
| tests/worker_evidence_test.py | 13 |
| tests/runtime_mode_test.py | 12 |
| tests/apply_outcome_journal_test.py | 11 |
| tests/worker_action_pipeline_test.py | 9 |
| tests/startup_reconciliation_test.py | 10 |
| tests/apply_verify_pipeline_test.py | 9 |
| tests/fault_injection_test.py | 9 |
| tests/llm_provider_test.py | 9 |
| tests/governance_evaluator_test.py | 8 |
| tests/worker_runtime_test.py | 7 |
| tests/patch_integrity_test.py | 6 |
| tests/secret_retry_boundary_test.py | 5 |
| tests/worker_runtime_integration_test.py | 4 |
| tests/property/governance_property_test.py | 4 |
| tests/llm_provider_integration_test.py | 2 (gated, skipped) |
| tests/planner_contract_test.py | 1 |
| recovery_test.py (root) | 1 |
| tests/mission_h_security_test.py | 25 (MISSION-H) |
| tests/mission_j2_rollback_test.py | 18 (MISSION-J.2 + J.3) |
| tests/mission_j31_rollback_authority_test.py | 18 (MISSION-J.3.1) |
| tests/mission_j_scope_test.py | 9 (MISSION-J/J.1) |
| tests/mission_j3_hardening_test.py | 4 (MISSION-J.3) |
| tests/replay_engine_test.py | 6 (replay suite) |
| tests/security/secret_guard_test.py | 39 (RELEASE-03 secret-guard corpus) |
| tests/snapshot_concurrency_test.py | 4 (RELEASE-03 snapshot isolation) |
| tests/security/memory_security_test.py | 34 (MISSION-M, concurrent) |
| tests/property/memory_property_test.py | 4 (MISSION-M, concurrent) |

Not collected by pytest (script-style files): calculator_test.py,
context_test.py, decision_trace_test.py, hash_test.py, loop_test.py,
memory_event_test.py, memory_events_test.py, memory_test.py,
planner_test.py, read_after_test.py, registry_test.py, replay_test.py,
snapshot_test.py, strategy_dispatcher_test.py, tool_executor_test.py,
test_run.py.

Test directories `tests/chaos/`, `tests/integration/`, `tests/property/`,
`tests/unit/` exist but are EMPTY (VERIFIED by directory listing).

---

# Current Git State

```
Branch:            worker-action-pipeline
HEAD:              24c72d0 (2026-08-21, "fix(edge-case): clamp provenance trust levels in from_dict") — 24c72d01690a6a1645317cb2b52c26c532731587
Working tree:      clean (nothing to commit); local == origin/worker-action-pipeline (MISSION N.55 verified)
.gitignore:        excludes .env, .env.*, *.pem, *.key, credentials.json,
                   secrets/, .venv/, data/, __pycache__/, *.pyc,
                   .pytest_cache/, .mypy_cache/, .ruff_cache/, logs, IDE files
                   (with !.env.example exception)
Local env:         .env present with OPENROUTER_API_KEY (untracked; ignored;
                   not part of any release snapshot)
CI:                .github/workflows/ci.yml (ubuntu + windows + packaging smoke step)
Packaging:         pyproject.toml (pip install -e . verified locally)
```

`main` is 30 commits behind `worker-action-pipeline`. No release tag exists
after v0.5.0 for the worker-action-pipeline work (HEAD 24c72d0 is 30 ahead).

---

# Known Limitations

VERIFIED where not marked:

1. **The risk gate and governed apply stay DEFAULT OFF / explicit opt-in by
   design (D-021/D-022).** The default runtime is proposal-only; `--governed`
   activates risk + approval + store-backed authorization. The gate is not
   default-on in the shipped assembly (productization decision).
2. **The interactive human-approval interface is CLI-only and synchronous:**
   `ConsoleApprovalGateway` blocks the governed run until the operator types
   approve/deny (or EOF, which fails closed). It is wired into
   `agent_run.py --governed`; programmatic callers must supply their own
   gateway or grant via `ApprovalStore.grant`.
3. **Approval durability requires a wired `ApprovalLedger`** (MISSION-016).
   Without a ledger the store is in-memory (tests cover both modes).
4. **Recovery is not active in the default runtime** (opt-in `--recovery` /
   `--governed`).
5. **DecisionTrace is in-memory**; durable evidence is only the event log.
6. **Event store has no dedup**; re-running a task appends fresh events
   (recovery-level duplicate fingerprints are rejected by
   `BoundedRecoveryEngine`). Appends are O(1), lock-serialized and fsynced
   (MISSION-016); multi-process writers on one store file are unsupported.
7. **`WorkerExecutor` hardcodes `task_id="worker-task"`** and
   `allowed_actions=("read","inspect","propose")`.
8. **Live LLM end-to-end** is covered by a gated harness
   (`tests/live_llm_e2e_test.py`) that passed once with a real provider; it
   never runs in the normal suite and is not a guarantee across providers.
9. **Secret redaction is heuristic, not a guarantee**; secret files are
   skipped wholesale but a missed inline pattern could still leak. Prompt
   injection resistance is a mitigation, not a proof.
10. **Docs drift:** README.md, CHANGELOG.md, docs/PROJECT_CONTEXT.md,
    docs/ROADMAP.md, docs/SESSION_NOTES.md, docs/MILESTONE-2.md still describe
    older versions/sprints.
11. **MISSION_LOG encoding corruption (mojibake)** in older entries, kept
    unchanged by policy.
12. **CI exists but has not been exercised externally** (no hosted run yet).
13. **No production benchmarks**; the append benchmark
    (`benchmarks/event_store_benchmark.py`) is a local sanity number.

---

# Unresolved Issues

- MISSION-011 (Risk/Policy Engine) and MISSION-012 (Human Approval
  Boundary) are CLOSED/VERIFIED as tested opt-in capabilities; whether the
  gate becomes default-on in the shipped assembly is deferred to a
  productization decision (D-021/D-022) — **UNKNOWN.**
- Whether recovery should become default (non-flag) behavior — explicitly a
  product decision (apply stays non-default by design).
- MISSION-009 was referenced as "state/documentation synchronization" but
  has no dedicated MISSION_LOG entry (commit `9b5c21e`).
- Whether the tracked `.pyc` artifacts and junk files (`git`, `kernel.txt`)
  should be removed from the repository.

---

# Immediate Next Work

Recommended (from audit findings, not a committed plan):

1. **Commit / push the MISSION-016 + MISSION-017 sprint** and run the new
   CI (incl. packaging smoke) on a hosted runner to close the symlink and
   Linux/macOS coverage gap.
2. **Decide the default-on gate** now that an interactive human-approval
   UX exists (MISSION-017): the risk gate stays explicit opt-in by design
   (D-021/D-022); default-on remains an open productization decision.
3. **Synchronize stale docs** (README, CHANGELOG, PROJECT_CONTEXT,
   docs/ROADMAP) with the verified baseline.
4. **MISSION-015 Productization Readiness Assessment.**
5. **Repository hygiene** (legacy `persistence/recovery.py`,
   `event_store_backup.py`, duplicate snapshot implementations,
   `services/` overlap) with dead-code evidence per component.

---

# Notes

This document is synchronized with actual code, git history and the
2026-08-21 MISSION N.55 foundation (986 collected / 974 passed / 12 skipped, HEAD 24c72d0). Stale documentation must not
be trusted over code and git history.
