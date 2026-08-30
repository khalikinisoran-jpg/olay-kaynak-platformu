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
| Last Updated | 2026-08-29 | VERIFIED |
| Active Branch | `worker-action-pipeline` | VERIFIED (`git branch --show-current`) |
| Branch HEAD | `9df6953` (`9df6953b4a51071330d7584f0ed2b569f4ab434b`, "fix(p5): enforce approval expiry parity") — current HEAD, 15 commits after the historical P9 FINAL PASS baseline `b2d6da7` (`b2d6da7234640e34fa349c067f56e23057053cf2`, 2026-08-25; implementation chain `07326ce..9df6953` = P10.2 docs sync + P10.3 hygiene A/B/C + OPERATOR-label p5 authority/integrity series P10.4-P10.6) | VERIFIED (`git rev-parse HEAD`, `git status`) |
| Remote | `origin` = https://github.com/khalikinisoran-jpg/olay-kaynak-platformu.git | VERIFIED (`git remote -v`) |
| Branch relationship | `worker-action-pipeline` is ahead of `main`; exact count is derived from `git log main..HEAD` (`main` has 0 commits not in `worker-action-pipeline`) | VERIFIED (`git log main..HEAD`, `git log HEAD..main`) |
| Historical Evidence Archive | `C:\Projects\event-sourcing-platform-evidence-archive` — **185 files** (144 MISSION-N* + 19 LAYER-A-* + 22 remaining = 185, missing 0, unreadable 0) — **PRESERVED_RELOCATED, PASS** (N.92 verified, N.94-R re-verified deterministic enumeration, artifact `n94r_enum_raw.txt` SHA `C5C22B…`) | VERIFIED (`Get-ChildItem -Recurse`, `n94r_enum_raw.txt`) |
| Latest release tag | v0.5.0 (2026-08-07, "Memory Recall Runtime") — no tag after v0.5.0 for this branch; `0.6.0` declared in `pyproject.toml` | VERIFIED (`git tag`) |
| Tags | v0.1.0-alpha, v0.3.0, v0.4.0, v0.5.0 | VERIFIED |
| Python | 3.12 (pyc artifacts indicate cpython-312); pytest 9.1.1 in `.venv` — current local full-suite evidence at HEAD `9df6953`: **`1278 collected / 1265 passed / 13 skipped / 0 failures` in 329.97s** (local Windows run 2026-08-30; local evidence only — NOT hosted CI, NOT a production-correctness proof). Historical: full-suite at `d42736d` `1272 collected / 1259 passed / 13 skipped / 0 failures` in 271.43s (2026-08-29); P9 FINAL PASS @ `b2d6da7`: `1213 collected / 1200 passed / 13 skipped / 0 failures` (hosted Ubuntu ~88s / Windows ~182s via run 32805095789, local ~254s with 300s budget; 120s is NOT COMPLETED) | VERIFIED (local `python -m pytest -q` at `9df6953`; historical: hosted run 32805095789) |

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
- **Governed CLI (P2.1/P2.2/P2.2-FP):** thin `agent_run.py` wrappers `apply`/`approve`/`history`/`status`/`task` over `WorkerActionPipeline`+`GovernanceEvaluator`+`ApprovalStore`+`ApplyOutcomeJournal` (isolated per-workspace `.cli_platform`). `task` runs Worker (`--fake-analyzer` deterministic) -> governed pipeline; `approve --pending` mechanically approves the exact `pending_proposals.json` proposal (fingerprint parity fix for shell quoting/BOM/newlines). Verified by `tests/test_cli_apply.py` (7), `tests/test_cli_task.py` (6), `tests/test_p22_exact_parity.py` (9), `tests/test_cli_observability.py` (5).
- **Governed external-action pipeline (post-P9, `b2d6da7..d42736d`):** `ExternalAction` (frozen contract; SHA-256 fingerprint over provider/operation/payload/idempotency_key/reason; synthetic `external://{provider}/{operation}` path projected onto the existing file-governance chain; `idempotency_key` deterministically bound into the synthetic fingerprint), `ExternalActionPipeline` (attempt authority ONLY via `intent_id` -> attempt 1, or a journal-issued `AttemptContext`; raw integer attempt rejected fail-closed; retry requires exact approval_id + attempt correlation), `ExternalActionExecutor` (fail-closed; requires `ExternalOutcomeJournal` — no in-memory fallback; records all four outcomes KNOWN_SUCCESS / KNOWN_FAILURE / TIMEOUT_UNKNOWN / AMBIGUOUS_UNKNOWN; ambiguous is never promoted to success; no auto-retry, no compensation), `ExternalOutcomeJournal` (append-only hash-chained JSONL, secret-safe payload/idempotency hashes, process-locked, fail-closed load; `open_attempt` issues a hash-bound `AttemptContext`; `start_opened_attempt` validates durable attempt / approval_id / previous-hash lineage before any provider call), `external_reconciliation.py` (durable lineage reconciliation) and `agent_run.py external` CLI wiring (isolated per-workspace `.cli_platform/external_journal.jsonl`). AgentSession is NOT the external attempt authority: production code never calls `AgentSession.next_attempt()`; `SessionGovernedBridge.execute_external` passes only `intent_id`/`attempt_context`. VERIFIED by the local full-suite PASS at `d42736d` (1272/1259/13/0) incl. `tests/test_external_t_b1..b10*`, `tests/test_external_model_b_production.py`, `tests/test_external_idempotency_binding.py`, `tests/test_external_f4_no_journal_bypass.py`, `tests/test_external_runtime_wiring_m12.py`, `tests/test_external_cli_t11a.py`.

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

Current authoritative run — **local full suite at HEAD `9df6953` (2026-08-30)** — `1278 collected / 1265 passed / 13 skipped / 0 failures` in **329.97s** (local Windows run; local evidence only — NOT hosted CI, NOT a production-correctness proof; valid only for the exact tested state HEAD `9df6953` + the then-current documentation working tree). Historical: full suite at `d42736d` (2026-08-29) — `1272 collected / 1259 passed / 13 skipped / 0 failures` in **271.43s**. Historical P9 FINAL PASS @ `b2d6da7` (2026-08-25): `1213 collected / 1200 passed / 13 skipped / 0 failures` (hosted exact-HEAD run **32805095789** Ubuntu ~88s / Windows ~182s, local ~254s with 300s budget; 120s is NOT COMPLETED). Foundation lineage: `24c72d0` established the earlier `986` collected baseline → P7 governed AgentSession → P8 multi-file atomicity → P9 FINAL PASS → post-P9 governed ExternalAction additions to 1272.

```
.venv\Scripts\python.exe -m pytest --collect-only -q
1278 collected  # current HEAD 9df6953 (incl. P10.3-P10.6 implementation chain)
.venv\Scripts\python.exe -m pytest -q
1265 passed, 13 skipped in 329.97s (1278 collected)  # local Windows run at 9df6953, 2026-08-30; local evidence only, NOT hosted CI
# historical P9 FINAL PASS @ b2d6da7: 1213 collected / 1200 passed / 13 skipped (hosted run 32805095789 Ubuntu ~88s / Windows ~182s)
powershell -ExecutionPolicy Bypass -File demo_cli.ps1 -> OVERALL PASS (conserved lineage from P2.3-A)
```

- 13 skipped: 3 opt-in `live_llm` integration tests (never run in the normal suite) + 10 symlink/OS-dependent tests that skip where the OS denies symlink creation (junction variants pass on Windows; symlink records now evidenced on hosted Ubuntu via run 32805095789).
- P9 FINAL PASS reproduced the baseline **`1213 collected / 1200 passed / 13 skipped / 0 failures`** via `python -m pytest -q` (FULL method with 300s budget) and exact-HEAD hosted CI; foundation `24c72d0` `986/974/12` retained as historical lineage, not current baseline.
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
HEAD:              9df6953 (2026-08-30, "fix(p5): enforce approval expiry parity") — 9df6953b4a51071330d7584f0ed2b569f4ab434b (15 commits after the historical P9 FINAL PASS baseline b2d6da7; chain 07326ce..9df6953 = P10.2 docs sync + P10.3 hygiene A/B/C + operator-label p5 fixes P10.4-P10.6)
Working tree:      clean at HEAD 9df6953 except unstaged P10.7-D canonical state synchronization edits (README.md / docs/ROADMAP.md / docs/PROJECT_MASTER.md / docs/PROJECT_STATE.md / docs/MISSION_STATUS.md); docs/ADR/ADR-001-Recovery-Orchestration.md clean; no staged files; 6 local commits ahead of origin/worker-action-pipeline (push = pending human decision)
.gitignore:        excludes .env, .env.*, *.pem, *.key, credentials.json,
                   secrets/, .venv/, data/, __pycache__/, *.pyc,
                   .pytest_cache/, .mypy_cache/, .ruff_cache/, logs, IDE files
                   (with !.env.example exception)
Local env:         .env present with OPENROUTER_API_KEY (untracked; ignored;
                   not part of any release snapshot)
CI:                .github/workflows/ci.yml (ubuntu + windows + packaging smoke step) — exact-HEAD hosted run 32805095789 succeeded (Ubuntu ~88s / Windows ~182s); local ~254s with 300s budget (120s is NOT COMPLETED)
Packaging:         pyproject.toml 0.6.0 (pip install -e . verified locally and via hosted packaging smoke)
Reproducible demo: demo_cli.ps1 (HIGH DENY -> approve --pending -> VERIFIED -> replay DENY, history read-only) — OVERALL PASS (conserved lineage; current evidence is P9 hosted run 32805095789)
```

`main` is behind `worker-action-pipeline` (exact count via `git log main..HEAD`); `main` has 0 commits not in `worker-action-pipeline`. No release tag exists after v0.5.0 for the worker-action-pipeline work (current HEAD `9df6953`; historical P9 FINAL PASS baseline `b2d6da7`; foundation `24c72d0` 30 commits ahead lineage, P2.3-A 41 ahead retained as historical distance).
Historical archive: `C:\Projects\event-sourcing-platform-evidence-archive` — 185 files preserved (N.92 PASS, N.94-R independent repro PASS).

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
10. **Docs drift (P10.2 progress):** README.md, START-HERE.md, and docs/PROJECT_MASTER.md synchronized to P9 FINAL PASS in P10.2-R1/R2; remaining drift in docs/PROJECT_CONTEXT.md (human-gated historical notice decision), docs/CHANGELOG.md (empty, human-gated redirect decision), CHANGELOG.md (historical chronology retained), docs/SESSION_NOTES.md and docs/MILESTONE-2.md (historical session snapshots, intentionally preserved) requires no automatic rewrite.
11. **MISSION_LOG encoding corruption (mojibake)** in older entries, kept
     unchanged by policy.
12. **CI:** exact-HEAD hosted run 32805095789 succeeded on Ubuntu (~88s) and Windows (~182s) at P9 FINAL PASS; local full suite ~254s with realistic 300s budget (120s is NOT COMPLETED / external budget limitation).
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
  should be removed from the repository — RESOLVED: removed in commit
  `a8de82e`; none remain tracked at HEAD.

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
5. **Repository hygiene** (completed for the audited candidates: legacy
   `persistence/recovery.py` and duplicate snapshot implementations
   removed in `542c187`/`07dbd34`; `event_store_backup.py` and
   `services/runtime_service.py` removed in P10.3-B with dead-code
   evidence per component).

---

# Notes

This document is synchronized with actual code, git history and the
current HEAD `9df6953` `9df6953b4a51071330d7584f0ed2b569f4ab434b` (local full-suite evidence `1278 collected / 1265 passed / 13 skipped / 0 failures` in 329.97s, 2026-08-30 — local only, NOT hosted CI, NOT a production-correctness proof). Historical evidence baselines are preserved unchanged: full-suite at `d42736d` `1272 collected / 1259 passed / 13 skipped / 0 failures` (2026-08-29) and P9 FINAL PASS baseline `b2d6da7` `b2d6da7234640e34fa349c067f56e23057053cf2` (2026-08-25; `1213 collected / 1200 passed / 13 skipped / 0 failures`; hosted run 32805095789 Ubuntu ~88s / Windows ~182s, local ~254s with 300s budget; 120s is NOT COMPLETED; foundation `24c72d0` 986 → P7 governed AgentSession + P8 multi-file atomicity + P9 additions to 1213; archive 185 = 144+19+22 PRESERVED_RELOCATED). Stale documentation must not be trusted over code and git history.

Demo: `python demo_vertical_slice.py` — governed vertical slice (Scenarios A LOW pass, B HIGH denied→approved, C rollback) using real `WorkerActionPipeline` (MISSION N.93); `demo_cli.ps1` — reproducible governed CLI demo (HIGH DENY -> pending -> VERIFIED -> replay DENY, P9 conserved, OVERALL PASS).
Archive: deterministic enumeration independently reproduced (`Get-ChildItem -Recurse`, `n94r_enum_raw.txt` SHA `C5C22BB9…`, 185 readable, 0 missing — confirms N.92, corrects N.94 UNRESOLVED to PASS). P9 exact-HEAD hosted CI evidenced (run 32805095789 Ubuntu ~88s / Windows ~182s).
