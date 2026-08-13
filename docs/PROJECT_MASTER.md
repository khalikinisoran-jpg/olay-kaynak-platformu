# PROJECT_MASTER.md

Canonical live project memory / first entry point for future engineers,
ChatGPT sessions and agents.

```
PROJECT_MASTER = HARITA (map)
SOURCE CODE    = GERCEKLIK (reality)
TESTS          = DAVRANIS KANITI (behavioral evidence)
GIT HISTORY    = DEGISIM TARIHI (change history)
```

PROJECT_MASTER never replaces source code. Every claim below is
classified:

- **VERIFIED** â€” confirmed by source code, passing tests, and/or commit
  history at the time of writing.
- **INFERRED** â€” reasoned from code/tests/history but not directly
  asserted by a single test.
- **UNKNOWN** â€” cannot be determined from repository evidence.

Source of truth order: Git history > source code > tests > docs. When this
document contradicts code, trust the code.

**STALE DATA POLICY:** if source code changes, any related claim in this
document may become stale. Refresh PROJECT_MASTER at every mission
close-out or after a significant architectural change. Cross-reference the
canonical docs (Section 4) rather than duplicating their full content.

---

# 1. BOOTSTRAP (read this first)

| Field | Value | Class |
|-------|-------|--------|
| CURRENT DATE | 2026-08-13 | VERIFIED |
| CURRENT BRANCH | `worker-action-pipeline` | VERIFIED (`git branch --show-current`) |
| CURRENT HEAD | `a8de82e2ea190db76df34304eca386b1199cd03a` (`a8de82e`, "Harden event store and snapshot integrity") | VERIFIED (`git rev-parse HEAD`) |
| WORKTREE STATE | MISSION-017 + MISSION-018A + MISSION-018B + MISSION-019 changes **uncommitted**: interactive CLI approval console, risk-boundary hardening, recovery authorization boundary, GovernanceEvaluator (single governance authority), ApplyOutcomeJournal + startup reconciliation (crash consistency), atomic snapshots, retry-evidence redaction, corpus A66-A72, new test suites, doc sync | VERIFIED (`git status --short`) |
| CURRENT MISSION | MISSION-019 **IMPLEMENTED / VERIFIED-by-suite** (uncommitted working tree); MISSION-018B IMPLEMENTED / VERIFIED-by-suite; MISSION-018A VERIFIED-by-suite; MISSION-017 VERIFIED-by-suite; MISSION-014 VERIFIED / CLOSED; MISSION-016 VERIFIED / CLOSED | VERIFIED (docs/MISSION_STATUS.md) |
| LAST VERIFIED TEST RESULT | full suite **648 passed / 10 skipped**; adversarial corpus **76 passed / 1 skipped** (A01-A72); `compileall` exit 0; `git diff --check` clean | VERIFIED (2026-08-13 run) |
| COMPLETED MISSIONS | 8 historic + 3 doc-sync + MISSION-003..014 + MISSION-016 + MISSION-017 + MISSION-018A + MISSION-018B + MISSION-019 (working tree) | VERIFIED (Section 18) |
| ACTIVE MISSIONS | none open; MISSION-015 (Productization Readiness Assessment) PLANNED | VERIFIED |
| OPEN SECURITY RISKS | risk classification remains a deterministic heuristic (a secret deliberately hidden under an innocent key in a plain file can still classify LOW); human operator identity is not authenticated (authorizer is informational); approval UX is CLI/synchronous only; symlink behavior beyond Windows junction coverage untested; approval state is durable only when a ledger is wired; orphaned-mutation auto-repair is intentionally NOT implemented (detect-only, D-032) | VERIFIED (Section 20) |
| UNKNOWN ITEMS | see Section 21 | — |
| NEXT 3-5 PRIORITIES | 1) commit/push MISSION-016..019 + hosted CI run, 2) default-on gate decision (UX now exists), 3) MISSION-015 productization readiness, 4) benchmark/CI hardening on Linux/macOS, 5) doc-sync + hygiene commit | INFERRED (Section 22) |

Quick orientation: the repository is an **event-sourced AI runtime
prototype**. A worker (optionally LLM-driven) proposes file modifications;
deterministic gates (validator -> controller -> apply -> verify) decide;
every decision becomes a hash-chained event. The MISSION-016 sprint wired
the risk/approval/authorization stack into a **real opt-in runtime path**
(`agent_run.py --governed`), added **rollback on verification failure**,
made approval single-use state **durable via an approval ledger**, hardened
the event store / snapshot integrity, added a **secret/prompt-injection
boundary** on the worker read path, and extended the adversarial corpus
(A01-A30). Apply/recovery/governed mode remain **opt-in only**; the default
runtime is proposal-only.

---

# 2. PROJECT PURPOSE

Build an event-sourced AI runtime in which every meaningful AI action
becomes an immutable, hash-chained event, so AI decisions can be replayed,
recovered, verified and audited, and constrained by deterministic system
controls. **VERIFIED** â€” docs/FOUNDING_PRINCIPLES.md, docs/PHILOSOPHY.md,
VISION.md, README.md; the full replay/verify/evidence machinery exists in
code (Section 4).

The product claim "trustworthy AI through Event Sourcing, Replay and
Verification" is the stated direction. **VERIFIED as project intent**;
external validation of the claim is **UNKNOWN** (no market research,
customer interviews or production deployment exist â€” docs/PRODUCT_POSITIONING.md).

---

# 3. PRODUCT DEFINITION

What actually exists (all **VERIFIED** from code/tests):

- An append-only, SHA-256 hash-chained event store with deterministic
  replay and snapshot recovery (`simulation/persistence/event_store.py`,
  `simulation/recovery/recovery_engine.py`, `simulation/replay/replay_engine.py`).
  Appends are O(1) (cached chain head), serialized by an internal lock, and
  fsynced; snapshots carry a content hash and are only trusted when it
  verifies (unverifiable snapshots fall back to full replay).
- A CLI chat runtime (`agent_run.py`) routing input through a Planner and a
  StrategyDispatcher of executors (calculator, memory store/recall, LLM,
  worker). Providers are created lazily: non-LLM strategies run without an
  API key.
- A worker agent that reads in-scope files and produces **patch proposals**
  only; it never applies. Secret files (`.env`, PEM keys, credential files)
  are skipped and secret-like values are redacted before any content reaches
  the LLM analyzer (optionally via real LLM OpenRouter/DeepSeek, gated tests).
- A deterministic apply/verify pipeline with bounded recovery and
  **rollback on verification failure** â€” active only when explicitly
  assembled (`build_recovery_agent()` or `agent_run.py --recovery`). Since
  MISSION-018B the authorization boundary is active in every apply-capable
  path: the apply boundary recomputes risk and DENIES HIGH/CRITICAL/UNKNOWN
  applies without a store-verified approval (a missing store is itself a
  denial), so RECOVERY can never mutate a security-sensitive patch without
  approval.
- A **governed runtime path** (`agent_run.py --governed`): the pipeline PLUS
  deterministic risk classification and a store-backed, single-use
  human-approval boundary with a **durable approval ledger**
  (single-use survives restarts), plus the interactive
  `ConsoleApprovalGateway`. `agent_run.py --recovery` wires the same risk +
  store + ledger without the interactive gateway (pre-authorized autonomous
  retry). Default runtime stays proposal-only.
- A documented security model with executable adversarial tests
  (`tests/security/adversarial_corpus_test.py`, A01-A65).
- A system-derived risk layer (`RiskEngine`/`RiskPolicy`/`RiskLevel`) with
  targeted boundary matching (kills `auth`/`token`/`secret`-in-word false
  positives), a small deterministic regression corpus, and a MISSION-018A
  fail-closed content classification: `not detected` is never treated as
  `safe` (SAFE / SUSPICIOUS -> HIGH approval / OPAQUE -> UNKNOWN DENY), so
  the audited credential-evasion classes no longer auto-apply in GOVERNED
  mode.
- A fingerprint-bound, single-use human-approval boundary
  (`Approval`/`ApprovalStore`/`ApprovalLedger`) hardened at the apply
  authorization boundary (MISSION-011/012/014/016).

What it is **not** (VERIFIED): a productized, packaged, deployed or
externally validated platform. No production configuration, API service,
multi-user story, or production benchmarks exist. CI and packaging metadata
were added in MISSION-016 (`.github/workflows/ci.yml`, `pyproject.toml`).

Unproven product/marketing claims (differentiators like "enterprise-grade",
"provider-agnostic beyond OpenRouter", "faster/safer than existing agent
frameworks") are **UNKNOWN/UNVERIFIED** â€” docs/PRODUCT_POSITIONING.md
sections 3 and 5.

---

# 4. ARCHITECTURE

Canonical detailed docs (use them as the reference; this section is the
index):

| Doc | Role |
|-----|------|
| docs/ARCHITECTURE.md | Canonical architecture of implemented code |
| docs/SECURITY_MODEL.md | Canonical security model (VERIFIED/INFERRED/UNKNOWN per claim) |
| docs/SECURITY_BASELINE.md | MISSION-005 security audit findings |
| docs/PROJECT_STATE.md | Current state, test counts, git state |
| docs/MISSION_STATUS.md | Mission-by-mission status |
| docs/MISSION_LOG.md | Detailed mission completion records (append-only) |
| docs/DECISION_LOG.md | Design decisions D-001..D-023 |
| docs/PROJECT_KNOWLEDGE_AUDIT.md | Repository maturity / gaps / facts audit |
| docs/PRODUCT_POSITIONING.md | Product claims vs evidence |
| docs/ROADMAP.md | Phased product roadmap (note: stale relative to code, see Section 20) |

Top-level code layout (**VERIFIED** by directory listing):

```
simulation/
  core/          Event, State, Reducer, Kernel (single write path)
  persistence/   EventStore (hash-chained JSONL), SnapshotStore/Manager, legacy backup/recovery
  replay/        ReplayEngine
  recovery/      RecoveryEngine (snapshot + hash-integrity + replay)
  snapshot/      snapshot manager (duplicate of persistence/snapshot_manager.py)
  security/      PathPolicy, HashChain, HashVerifier, RiskLevel, RiskEngine,
                 RiskPolicy, SecretPolicy (read-side secret boundary)
  decision/      DecisionTrace (in-memory)
  loop/          LoopEngine
  planner/       Planner
  context/       ContextBuilder
  memory/        MemoryService + MemoryEvents
  tools/         BaseTool, Registry, Calculator
  llm/           BaseProvider, OpenRouterProvider, ProviderFactory (lazy)
  agent/
    agent.py            Agent runtime (chat, dispatches worker/recovery/pipeline)
    strategy_dispatcher.py
    executors/          calculator, memory_store, memory_recall, llm, worker
    worker/             WorkerAgent, WorkerTask, WorkerResult, PatchProposal,
                        PatchValidator, PatchGenerator, LLMCodeAnalyzer,
                        AnalysisResult, ValidationResult, WorkerPolicy
    controller/         Controller, ControllerDecision
    approval/           Approval, ApprovalStore, ApprovalLedger, ApprovalConsole
                        (MISSION-012/014/016/017)
    apply/              ApplyAuthorization, ApplyExecutor, FileApplier, ApplyResult
    verify/             VerificationExecutor, CommandRunner, VerificationResult
    pipeline/           WorkerActionPipeline, ApplyVerifyPipeline, ApplyVerifyResult,
                        RollbackResult
    recovery/           BoundedRecoveryEngine, RecoveryAttempt, RecoveryResult, recovery_assembly
    evidence/           WorkerEventType, build_worker_event, WorkerEvidenceRecorder
  domain/               legacy domain models (worker.py, task.py, enums.py)
  services/             legacy tool_executor/runtime_service (overlap with agent/executors/)
agent_run.py            CLI entry point (default proposal-only; --recovery; --governed)
benchmarks/             event_store_benchmark.py (standalone append benchmark)
.github/workflows/      ci.yml (ubuntu + windows)
pyproject.toml          packaging metadata
```

`Kernel.dispatch` is the single write path for all events, including worker
evidence events (`simulation/core/kernel.py:40`). **VERIFIED.**

---

# 5. RUNTIME EXECUTION FLOW

Verified against source (each link names the real file + symbol):

```
user prompt
  -> Agent.chat()                         simulation/agent/agent.py::Agent.chat
      -> kernel.dispatch(UserQuestionReceived)          simulation/core/kernel.py::Kernel.dispatch
      -> Planner.plan -> strategy        simulation/planner/planner.py::Planner.plan
      -> StrategyDispatcher.dispatch     simulation/agent/strategy_dispatcher.py
          -> (worker strategy) WorkerExecutor.execute -> WorkerAgent.run
               simulation/agent/executors/worker/worker_executor.py::WorkerExecutor.execute
               simulation/agent/worker/worker_agent.py::WorkerAgent.run
  -> WorkerResult (patch proposals only)
  Agent.chat branch:
     recovery_engine set  -> BoundedRecoveryEngine.execute  (opt-in)
     worker_pipeline set  -> WorkerActionPipeline.execute   (opt-in)
     else                 -> proposal-only, no mutation     (default)
```

WorkerActionPipeline per-patch chain
(`simulation/agent/pipeline/worker_action_pipeline.py::WorkerActionPipeline.execute`):

```
patch (PatchProposal)
  -> PatchValidator.validate                        patch_validator.py::validate
  -> [opt-in risk gate] RiskEngine.classify         risk_engine.py::classify
       -> RiskPolicy.decide                          risk_policy.py::decide
       -> UNKNOWN/DENY => stop (failure_stage="risk")
       -> HIGH/CRITICAL => ApprovalStore.find_valid(..., patch=patch)
            approval_store.py::find_valid           (consumes + object-binds)
            -> _approval_is_valid                    worker_action_pipeline.py (typed + full binding)
            -> missing/malformed/expired/wrong/replayed => stop (failure_stage="approval")
  -> Controller.approve(patch, validation, approval?) controller.py::approve
       (binds consumed approval_id into decision)
  -> ApplyVerifyPipeline.execute(patch, decision)    apply_verify_pipeline.py::execute
       -> ApplyExecutor.apply                        apply_executor.py::apply
           -> ApplyAuthorization.authorize           apply_authorization.py::authorize
                (typed ControllerDecision + approved is True + fingerprint match;
                 store-backed: risk recomputed at boundary + ApprovalStore.authorize_apply
                 for HIGH/CRITICAL/UNKNOWN)
           -> FileApplier.apply                      file_applier.py::apply
                (scope re-check, canonical write-through, read-back + restore)
       -> (if applied) VerificationExecutor.verify / verify_python_compile
            verification_executor.py::verify
  -> PatchStageResult; first failure stops the run
```

Recovery/retry (opt-in) (`bounded_recovery_engine.py::BoundedRecoveryEngine.execute`):

```
worker -> pipeline -> if verification FAIL and budget remains -> retry
budget: hard cap 3 (MAX_ATTEMPTS_CAP); duplicate fingerprints stop; non-verification failures terminal
```

All of the above is **VERIFIED** by the passing suites (Section 16) and the
adversarial corpus (Section 15).

---

# 6. COMPONENT MAP

23 components, each with NAME / PURPOSE / SOURCE FILE / SYMBOLS / INPUT /
OUTPUT / SECURITY ROLE / FAIL-CLOSED BEHAVIOR / RELATED TESTS / LAST
VERIFIED COMMIT / STATUS.

Legend: `~` = last commit that touched the file; MISSION-012/013/014
changes are **uncommitted working tree** on top of `f94c82b`.

## 6.1 Worker
- PURPOSE: Read in-scope files, analyze them (LLM or fake), produce patch proposals. Never applies.
- SOURCE: `simulation/agent/worker/worker_agent.py` (`WorkerAgent`), `simulation/agent/executors/worker/worker_executor.py` (`WorkerExecutor`)
- SYMBOLS: `WorkerAgent.run()`, `WorkerAgent.REQUIRED_ACTIONS`, `WorkerAgent._task_allows`, `WorkerAgent._analysis_description`; `WorkerExecutor.execute()`
- INPUT: `WorkerTask` (worker_task.py)
- OUTPUT: `WorkerResult` (proposals + evidence, worker_result.py)
- SECURITY ROLE: proposal producer; scope + action + analysis-contract enforcement (MISSION-005/010)
- FAIL-CLOSED: empty `allowed_paths` -> "No allowed paths were provided."; policy/task action denied -> fail; analyzer not `AnalysisResult` -> fail; `old_text` not occurring exactly once -> fail
- RELATED TESTS: worker_contract_test.py (31), worker_read_scope_test.py (16), structured_analysis_test.py (41), adversarial A05b/A06
- LAST VERIFIED COMMIT: `fc8f593` (worker/analysis hardening; worker_agent latest edits `5c475b6`..`93a9d4b`); STATUS: VERIFIED

## 6.2 WorkerActionPipeline
- PURPOSE: Trusted orchestrator that binds a WorkerResult to validation -> risk -> approval -> controller -> apply+verify, fail-closed per patch.
- SOURCE: `simulation/agent/pipeline/worker_action_pipeline.py`
- SYMBOLS: `WorkerActionPipeline.execute()`, `_approval_is_valid`, `_bind_approval_authority`, `_classify_failure`; `PatchStageResult`, `WorkerPipelineResult`
- INPUT: `WorkerResult` (+ `verify_paths`, `test_targets`, `attempt`)
- OUTPUT: `WorkerPipelineResult` (success, failure_stage, evidence, exit_code, stdout/stderr)
- SECURITY ROLE: narrowest orchestration boundary; enforces gate order; binds the store into the apply executor when the gate is enabled (MISSION-014)
- FAIL-CLOSED: no patches -> worker failure; validation fail / risk deny / approval missing / controller reject -> stop before apply
- RELATED TESTS: worker_action_pipeline_test.py (11), risk_pipeline_test.py (15), approval_boundary_test.py (48), worker_runtime_integration_test.py (4)
- LAST VERIFIED COMMIT: `96ed72d` + working-tree (MISSION-012/014); STATUS: VERIFIED

## 6.3 PatchProposal
- PURPOSE: Immutable patch data contract with deterministic fingerprint.
- SOURCE: `simulation/agent/worker/patch_proposal.py`
- SYMBOLS: `PatchProposal` (frozen dataclass), `fingerprint()` (SHA-256 over all fields)
- INPUT/OUTPUT: data object passed through every gate
- SECURITY ROLE: identity anchor â€” the fingerprint binds validation/risk/approval/decision/apply
- FAIL-CLOSED: none (pure data); malformed values rejected upstream
- RELATED TESTS: worker_contract_test, patch_integrity_test, adversarial A12/A14
- LAST VERIFIED COMMIT: `27effbf`; STATUS: VERIFIED

## 6.4 PatchValidator
- PURPOSE: Pre-controller gate: scope, action, existence, staleness, no-op rejection.
- SOURCE: `simulation/agent/worker/patch_validator.py`
- SYMBOLS: `PatchValidator.validate()`, `ALLOWED_ACTIONS = {"modify"}`
- INPUT: `PatchProposal`; OUTPUT: `(bool, message)`
- SECURITY ROLE: first deterministic gate
- FAIL-CLOSED: empty path; unsupported action; out-of-scope; missing/not-file; stale (`current != old_content`); no-op (`old == new`)
- RELATED TESTS: worker_contract_test, path_security_test.py (31), patch_integrity_test.py (6), adversarial A05/A07
- LAST VERIFIED COMMIT: `f5d1fbc`; STATUS: VERIFIED

## 6.5 Patch integrity / fingerprint
- PURPOSE: Guarantee "approved patch == applied patch" and exact old_content at write time.
- SOURCE: `file_applier.py::FileApplier` (read-back + restore), `path_policy.py::PathPolicy.resolve_target` (canonical write-through), `patch_proposal.py::fingerprint`
- SECURITY ROLE: write-time integrity boundary (MISSION-006)
- FAIL-CLOSED: stale -> deny before write; written != new_content -> restore old_content + FAIL
- RELATED TESTS: patch_integrity_test.py (6), adversarial A07/A08b/A12/A12b
- LAST VERIFIED COMMIT: `f5d1fbc`; STATUS: VERIFIED

## 6.6 Controller
- PURPOSE: Decide approval from a typed ValidationResult; bind a consumed approval id when present.
- SOURCE: `simulation/agent/controller/controller.py`
- SYMBOLS: `Controller.approve(patch, validation, approval=None)`
- INPUT: `PatchProposal` + `ValidationResult` (+ optional `Approval`); OUTPUT: `ControllerDecision`
- SECURITY ROLE: trusted decision producer (MISSION-007/014)
- FAIL-CLOSED: None/malformed validation; `valid is not True`; non-`modify` action; non-`Approval` or wrong-fingerprint approval
- RELATED TESTS: controller_decision_test.py (13), approval_boundary_test.py (A/B)
- LAST VERIFIED COMMIT: `2249a04` + working-tree (MISSION-014); STATUS: VERIFIED

## 6.7 ControllerDecision
- PURPOSE: Immutable decision contract carrying approval identity.
- SOURCE: `simulation/agent/controller/controller_decision.py`
- SYMBOLS: `ControllerDecision` (frozen): `approved`, `reason`, `patch_fingerprint`, `approval_id`
- SECURITY ROLE: only the trusted controller sets `approved`/`approval_id`; the apply boundary never trusts duck-typed equivalents
- FAIL-CLOSED: `approved is not True` / missing or wrong fingerprint / (store-backed) missing approval_id -> deny
- RELATED TESTS: controller_decision_test.py, approval_boundary_test.py (A/B/O)
- LAST VERIFIED COMMIT: `2249a04` + working-tree (MISSION-014); STATUS: VERIFIED

## 6.8 RiskLevel
- PURPOSE: Deterministic ordered risk classification.
- SOURCE: `simulation/security/risk_level.py`
- SYMBOLS: `RiskLevel` enum (UNKNOWN<LOW<MEDIUM<HIGH<CRITICAL), `parse()`, `severity`, `at_least()`, `max_level()`
- SECURITY ROLE: fail-closed base of the risk layer
- FAIL-CLOSED: `parse` raises on None/non-string/unknown label; `max_level` ignores malformed inputs
- RELATED TESTS: risk_level_test.py (20)
- LAST VERIFIED COMMIT: `96ed72d`; STATUS: VERIFIED

## 6.9 RiskEngine
- PURPOSE: System-derived risk classification from observable signals.
- SOURCE: `simulation/security/risk_engine.py`
- SYMBOLS: `RiskEngine.classify(patch, advisory_risk, advisory_confidence)`, `RiskAssessment`
- INPUT: `PatchProposal`; OUTPUT: `RiskAssessment(risk_level, signals, advisory*)`
- SECURITY ROLE: risk authority is system-derived; LLM advisory can only raise (MISSION-011)
- FAIL-CLOSED: `patch is None` / missing-malformed-empty action -> UNKNOWN (policy => DENY); malformed advisory dropped
- RELATED TESTS: risk_engine_test.py (30)
- LAST VERIFIED COMMIT: `96ed72d`; STATUS: VERIFIED

## 6.10 RiskPolicy
- PURPOSE: Map risk to enforceable requirements (allow, approval, retries, depth).
- SOURCE: `simulation/security/risk_policy.py`
- SYMBOLS: `RiskPolicy.decide(assessment)`, `from_level(level)`, `RiskDecision`
- INPUT: `RiskAssessment`; OUTPUT: `RiskDecision`
- SECURITY ROLE: hard gate (UNKNOWN=>DENY; HIGH/CRITICAL=>human approval; LOW/MEDIUM=>auto)
- FAIL-CLOSED: missing/malformed assessment -> DENY; UNKNOWN -> DENY (never auto-approvable); max_attempts capped
- RELATED TESTS: risk_policy_test.py (18)
- LAST VERIFIED COMMIT: `96ed72d`; STATUS: VERIFIED

## 6.11 Approval
- PURPOSE: Frozen, single-use human-approval authorization contract.
- SOURCE: `simulation/agent/approval/approval.py`
- SYMBOLS: `Approval` (frozen dataclass: approval_id, patch_fingerprint, path, action, risk_level, attempt, authorizer, created_at, expires_at), `Approval.create()`, `is_expired()`, `now_iso()/iso_in_future()/iso_in_past()`
- SECURITY ROLE: the human-approval authorization token (MISSION-012)
- FAIL-CLOSED: `__post_init__` raises on malformed fingerprint/path/action/risk/attempt/authorizer/timestamps; only HIGH/CRITICAL risk valid
- RELATED TESTS: approval_boundary_test.py (model tests)
- LAST VERIFIED COMMIT: working tree (MISSION-012); STATUS: VERIFIED

## 6.12 ApprovalStore
- PURPOSE: Durable human-approval authority; grant + context-bound single-use release + apply-boundary consumption.
- SOURCE: `simulation/agent/approval/approval_store.py`
- SYMBOLS: `grant(...)`, `find_valid(fingerprint, path, action, risk_level, attempt, patch=None)`, `authorize_apply(approval_id, patch)`, `is_consumed()`, `is_applied()`
- INPUT: full authorization context (+ exact patch object); OUTPUT: `Approval` or `None` / bool
- SECURITY ROLE: narrowest enforcement point for approval authority (MISSION-014)
- FAIL-CLOSED: incomplete context -> None; expired -> None; consumed/replayed -> None; `authorize_apply` requires grant-by-this-store + released-by-`find_valid` + exact patch object binding + not-already-applied + non-expired + fingerprint/path/action match; then consumes once
- RELATED TESTS: approval_boundary_test.py (48), corpus A13-A19
- LAST VERIFIED COMMIT: working tree (MISSION-012/014); STATUS: VERIFIED

## 6.13 ApplyAuthorization
- PURPOSE: Fail-closed apply authorization boundary.
- SOURCE: `simulation/agent/apply/apply_authorization.py`
- SYMBOLS: `ApplyAuthorization.authorize(decision, patch)`; `__init__(approval_store=None, risk_engine=None)`
- INPUT: decision + `PatchProposal`; OUTPUT: bool
- SECURITY ROLE: typed-decision check + store-backed approval verification; risk recomputed deterministically at the boundary (MISSION-014)
- FAIL-CLOSED: non-`ControllerDecision` (fake object); `approved is not True`; missing/mismatched fingerprint; store-backed HIGH/CRITICAL/UNKNOWN requires `decision.approval_id` + `approval_store.authorize_apply`
- RELATED TESTS: approval_boundary_test.py (MISSION-014 A-O), controller_decision_test.py
- LAST VERIFIED COMMIT: working tree (MISSION-014); STATUS: VERIFIED

## 6.14 ApplyExecutor
- PURPOSE: Bridge authorization -> real file write.
- SOURCE: `simulation/agent/apply/apply_executor.py`
- SYMBOLS: `ApplyExecutor.__init__(approval_store=None)`, `ApplyExecutor.apply(patch, decision)`
- SECURITY ROLE: constructs store-backed authorization when configured (MISSION-014)
- FAIL-CLOSED: authorization deny -> `ApplyResult(success=False)` with no write
- RELATED TESTS: worker_contract_test, patch_integrity_test, approval_boundary_test, apply_verify_pipeline_test
- LAST VERIFIED COMMIT: `f5d1fbc` + working-tree (MISSION-014); STATUS: VERIFIED

## 6.15 FileApplier
- PURPOSE: Real file write with write-time integrity.
- SOURCE: `simulation/agent/apply/file_applier.py`
- SYMBOLS: `FileApplier.apply(patch)`, `_restore(path, old_content)`
- SECURITY ROLE: re-checks scope, requires exact old_content, writes through canonical path, reads back and restores (MISSION-006)
- FAIL-CLOSED: unsupported action; out-of-scope; unresolved canonical; missing/not-file; stale; written != new_content -> restore + FAIL
- RELATED TESTS: patch_integrity_test.py (6), path_security_test.py (31), adversarial A01-A04/A07/A08b/A12b
- LAST VERIFIED COMMIT: `f5d1fbc`; STATUS: VERIFIED

## 6.16 ApplyVerifyPipeline
- PURPOSE: Run verification only after successful apply; never conflate the two.
- SOURCE: `simulation/agent/pipeline/apply_verify_pipeline.py`
- SYMBOLS: `ApplyVerifyPipeline.execute(patch, decision, verify_paths, test_targets, verification_depth)`, `VERIFICATION_DEPTH_COMPILE` / `VERIFICATION_DEPTH_COMPILE_TESTS`; `ApplyVerifyResult`
- SECURITY ROLE: apply/verify separation (D-005)
- FAIL-CLOSED: apply failure -> no verification runs
- RELATED TESTS: apply_verify_pipeline_test.py (9), risk_pipeline_test.py, adversarial A08/A09
- LAST VERIFIED COMMIT: `96ed72d`; STATUS: VERIFIED

## 6.17 VerificationExecutor
- PURPOSE: Deterministic post-apply verification (compileall + pytest).
- SOURCE: `simulation/agent/verify/verification_executor.py`, `command_runner.py`
- SYMBOLS: `verify()`, `verify_python_compile()`, `verify_tests()`, `_is_pass`, `CommandRunner.run`
- INPUT: paths + test targets; OUTPUT: `VerificationResult` (+ `VerificationEvidence`)
- SECURITY ROLE: verification authority is deterministic; never a Worker/LLM claim (A09)
- FAIL-CLOSED: PASS only when exit code 0 and no timeout/error; commands as arg lists (shell=False)
- RELATED TESTS: verification_executor_test.py (15), adversarial A08/A09
- LAST VERIFIED COMMIT: `9df8390` + `96ed72d` (depth); STATUS: VERIFIED

## 6.18 BoundedRecoveryEngine
- PURPOSE: Bounded iterative retry on verification FAIL only.
- SOURCE: `simulation/agent/recovery/bounded_recovery_engine.py`
- SYMBOLS: `execute()`, `MAX_ATTEMPTS_CAP = 3`, `_bounded_max_attempts`, `_first_duplicate`, `_record_attempt`
- SECURITY ROLE: retry decision is orchestrated, never Worker/LLM (D-006)
- FAIL-CLOSED: caller max_attempts clamped to 3; non-verification failures terminal; duplicate fingerprint stops; exceptions terminal
- RELATED TESTS: recovery_engine_test.py (33), adversarial A10
- LAST VERIFIED COMMIT: `90400c9` + working-tree (evidence recorder); STATUS: VERIFIED

## 6.19 Recovery assembly
- PURPOSE: The ONLY production wiring that enables apply+verify+recovery; explicit opt-in.
- SOURCE: `simulation/agent/recovery/recovery_assembly.py`
- SYMBOLS: `build_recovery_agent(kernel, worker_executor, apply_executor, verification_executor, controller, max_attempts, provider, evidence_recorder, risk_engine, risk_policy, approval_store)`
- SECURITY ROLE: default gate OFF (needs BOTH risk_engine+risk_policy); creates store only when gate enabled; builds store-backed ApplyExecutor (MISSION-014)
- FAIL-CLOSED: no risk args -> gate off, store None; `--recovery` without `--allowed-path` -> worker fail-closed
- RELATED TESTS: approval_boundary_test.py (assembly tests), risk_pipeline_test.py (assembly tests)
- LAST VERIFIED COMMIT: `96ed72d` + working-tree (MISSION-012/014); STATUS: VERIFIED

## 6.20 Evidence recorder
- PURPOSE: Bridge pipeline/recovery decisions into the Kernel event store + DecisionTrace.
- SOURCE: `simulation/agent/evidence/worker_evidence_recorder.py`
- SYMBOLS: `WorkerEvidenceRecorder`, `record_task_created`, `record_inspection`, `record_patch_proposed/validated`, `record_controller_decision`, `record_apply_result`, `record_verification_result`, `record_approval_granted`, `record_recovery_attempt/outcome`, `_emit`
- SECURITY ROLE: evidence records authority but never becomes authority (D-012/D-013, MISSION-014 M-test)
- FAIL-CLOSED: payloads never contain patch content / stdout / stderr / secrets; unknown event types rejected
- RELATED TESTS: worker_evidence_test.py (13), adversarial A11
- LAST VERIFIED COMMIT: `ea9b2ab` + working-tree (MISSION-012); STATUS: VERIFIED

## 6.21 Worker events
- PURPOSE: Typed worker lifecycle event definitions.
- SOURCE: `simulation/agent/evidence/worker_events.py`
- SYMBOLS: `WorkerEventType` (14 types incl. `WorkerHumanApprovalGranted`), `build_worker_event(event_type, payload)`
- SECURITY ROLE: allow-list factory; secret-safe payload contract
- FAIL-CLOSED: unknown event type raises
- RELATED TESTS: worker_evidence_test.py (13)
- LAST VERIFIED COMMIT: `ea9b2ab` + working-tree (MISSION-012); STATUS: VERIFIED

## 6.22 Adversarial corpus
- PURPOSE: Executable threat-model benchmark (A01-A65), summary-gated.
- SOURCE: `tests/security/adversarial_corpus_test.py`
- SYMBOLS: `Corpus`, `CorpusRecord`, `test_a01...test_a20`, `test_corpus_summary`
- SECURITY ROLE: regression guard â€” the summary test fails the suite if any recorded attack regressed
- RELATED TESTS: 25 test functions / 23 records; **VERIFIED** (24 passed, 1 symlink skip)
- LAST VERIFIED COMMIT: `27effbf` + working-tree (MISSION-013); STATUS: VERIFIED

## 6.23 Retry / attempt model
- PURPOSE: Immutable, append-only attempt evidence for the bounded loop.
- SOURCE: `simulation/agent/recovery/bounded_recovery_engine.py`, `simulation/agent/recovery/recovery_attempt.py`, `simulation/agent/recovery/recovery_result.py`
- SYMBOLS: `AttemptStatus` (SUCCESS/FAILED/BLOCKED/ERROR), `RecoveryAttempt`, `RecoveryResult` (success/terminal_failure/retry_count/final_attempt...)
- SECURITY ROLE: append-only evidence; attempt history never mutated
- FAIL-CLOSED: no recursion; hard cap; duplicate fingerprint suppression
- RELATED TESTS: recovery_engine_test.py (33)
- LAST VERIFIED COMMIT: `90400c9` + working-tree; STATUS: VERIFIED

## 6.24 ApprovalConsole (CLI human-approval interface)
- PURPOSE: Turn a HIGH/CRITICAL proposal into a human-readable request and route an explicit human approve/deny into `ApprovalStore.grant`; wired into the governed runtime via `ConsoleApprovalGateway`.
- SOURCE: `simulation/agent/approval/approval_console.py`
- SYMBOLS: `PendingApprovalRequest` (render/to_grant_context), `build_pending_request`, `prompt_approval_decision`, `ConsoleApprovalGateway.request_approval`
- INPUT: `PatchProposal` + `RiskAssessment` (+ attempt/authorizer/TTL/evidence ref); OUTPUT: `Approval` or `None`
- SECURITY ROLE: minimal UX layer; never an authority; derives every displayed/granted value from the real patch + system risk; refuse on risk mismatch; deny/EOF fail closed (MISSION-017)
- FAIL-CLOSED: non-`PatchProposal`/`RiskAssessment` input raises; unrecognized input re-prompts; EOF/deny -> None; risk mismatch -> None; grant still goes through `find_valid`/`authorize_apply`
- RELATED TESTS: tests/approval_console_test.py (23), corpus A31-A36
- LAST VERIFIED COMMIT: working tree (MISSION-017); STATUS: VERIFIED

## 6.25 GovernanceEvaluator (single governance authority)
- PURPOSE: Wrap ONE `RiskEngine` + `RiskPolicy`; the only risk authority consumed by the pipeline gate, the approval console and the apply boundary, so the three layers can never diverge on classification (MISSION-019).
- SOURCE: `simulation/security/governance_evaluator.py`
- SYMBOLS: `GovernanceEvaluator` (evaluate/classify/decide/authorize_apply), `GovernanceDecision`
- INPUT: `PatchProposal`; OUTPUT: `GovernanceDecision` / bool
- SECURITY ROLE: single deterministic governance authority; `authorize_apply` is the shared apply-boundary risk branch (LOW/MEDIUM => typed-decision contract; HIGH/CRITICAL/UNKNOWN => store-verified approval; store-less => DENY)
- FAIL-CLOSED: MISSION-018A (SAFE/SUSPICIOUS/OPAQUE, not-detected!=safe) and MISSION-018B (store-less DENY) semantics unchanged; only fixes *which* engine/policy is consulted
- RELATED TESTS: tests/governance_evaluator_test.py (8), corpus A71
- LAST VERIFIED COMMIT: working tree (MISSION-019); STATUS: VERIFIED

## 6.26 ApplyOutcomeJournal (crash-consistent apply lifecycle)
- PURPOSE: Append-only, hash-chained, secret-safe record of the apply lifecycle (INTENT -> APPLY_STARTED -> APPLIED/APPLY_FAILED -> VERIFIED/ROLLBACK_STARTED -> ROLLED_BACK/ROLLBACK_FAILED) so a crash between a file write and the evidence event is detectable after restart (MISSION-019).
- SOURCE: `simulation/agent/apply/apply_outcome_journal.py`
- SYMBOLS: `ApplyOutcomeJournal` (record_intent/apply_started/applied/apply_failed/verified/rollback_started/rolled_back/rollback_failed, load, intents)
- INPUT: patch + attempt + approval_id; OUTPUT: journal records (content hashes only)
- SECURITY ROLE: durable outcome evidence, NEVER an authorization input (D-012 preserved); fail-closed on corruption/out-of-order/duplicate
- FAIL-CLOSED: malformed/hash-broken/unknown-type/unknown-intent/out-of-order transitions raise `RuntimeError` on load
- RELATED TESTS: tests/apply_outcome_journal_test.py (11), corpus A66/A68/A69
- LAST VERIFIED COMMIT: working tree (MISSION-019); STATUS: VERIFIED

## 6.27 ReconciliationEngine (detect-only startup reconciliation)
- PURPOSE: After a restart, classify journaled apply intents, inspect in-scope files against journaled content hashes, and flag orphaned mutations / consumed approvals without a terminal outcome (MISSION-019).
- SOURCE: `simulation/agent/recovery/startup_reconciliation.py`
- SYMBOLS: `ReconciliationEngine.detect()`, `ReconciliationReport`, `IntentStatus`
- INPUT: journal (+ allowed scope + optional approval store); OUTPUT: report (detect-only)
- SECURITY ROLE: detection never writes a file and never re-authors an apply; repair is deliberately out of scope (a mutation requiring explicit authorization)
- FAIL-CLOSED: corrupt journal => `RuntimeError` (no best-effort report)
- RELATED TESTS: tests/startup_reconciliation_test.py (10), tests/fault_injection_test.py (9), corpus A67/A70
- LAST VERIFIED COMMIT: working tree (MISSION-019); STATUS: VERIFIED

---

# 7. TRUST MODEL

Boundary chain derived from code. For each boundary: WHO CONTROLS IT /
WHAT CAN BE FORGED / WHAT VALIDATION EXISTS / WHAT FAIL-CLOSED MEANS /
TEST EVIDENCE.

## 7.1 Agent-controlled data (Worker)
- WHO CONTROLS: the Worker/LLM (untrusted); produces `WorkerResult` with patches.
- WHAT CAN BE FORGED: arbitrary proposal content, `human_approved`/`approval_token`-style claims attached to proposals, malformed analysis.
- VALIDATION: `WorkerAgent.run` enforces `WorkerPolicy` + task `allowed_actions` + read scope (`PathPolicy.check_scope`); requires typed `AnalysisResult`; `old_text` exactly once; `PatchValidator` re-checks later (worker_agent.py, analysis_result.py).
- FAIL-CLOSED: any denial yields `success=False` with no patch; proposal-contained approval claims are ignored (pipeline only accepts a store-returned `Approval`).
- TEST EVIDENCE: worker_contract_test.py, worker_read_scope_test.py, structured_analysis_test.py, adversarial A05b/A06/A20.

## 7.2 Worker -> Controller
- WHO CONTROLS: `WorkerActionPipeline` (trusted orchestrator) builds `ValidationResult` from the validator; `Controller` is trusted.
- WHAT CAN BE FORGED: a `ValidationResult` with a truthy-but-not-True `valid`, or a duck-typed fake.
- VALIDATION: `Controller.approve` requires `isinstance(validation, ValidationResult)` and `validation.valid is True`; message text never consulted.
- FAIL-CLOSED: None/malformed/not-True -> rejected decision; no apply.
- TEST EVIDENCE: controller_decision_test.py (13), worker_contract_test.py.

## 7.3 Controller
- WHO CONTROLS: trusted component; decisions are the binding authority for the (non-approval) path.
- WHAT CAN BE FORGED: a forged `ControllerDecision` (real or duck-typed) injected at the apply boundary.
- VALIDATION: `ApplyAuthorization` requires `isinstance(decision, ControllerDecision)`, `approved is True`, fingerprint == `patch.fingerprint()`; store-backed path additionally requires a verified approval binding for HIGH/CRITICAL/UNKNOWN (risk recomputed at the boundary, so the risk cannot be forged by the decision).
- FAIL-CLOSED: any fake/forged decision, or a decision without the approval binding for an approval-required patch, is denied before any write.
- TEST EVIDENCE: approval_boundary_test.py (A/B/O), adversarial A12.

## 7.4 Risk
- WHO CONTROLS: `RiskEngine` (system-derived, deterministic); LLM advisory is a non-authoritative input that can only raise.
- WHAT CAN BE FORGED: a downgraded risk level or malformed assessment.
- VALIDATION: `RiskLevel.parse` raises on garbage; `RiskEngine.classify` derives from path/action/content; `RiskPolicy.decide` requires a `RiskAssessment`; UNKNOWN -> DENY.
- FAIL-CLOSED: malformed/missing -> UNKNOWN -> DENY before apply.
- TEST EVIDENCE: risk_engine_test.py (30), risk_policy_test.py (18), risk_pipeline_test.py (15).

## 7.5 Human Approval
- WHO CONTROLS: `ApprovalStore` (trusted authority). The worker/agent cannot grant or consume.
- WHAT CAN BE FORGED: a forged `Approval`, an agent-claimed `approval_id`, store-fabricated dict metadata, proposal-contained claims.
- VALIDATION: typed `Approval` + full binding at `_approval_is_valid`; `find_valid` requires complete context + consumes; `authorize_apply` requires grant-by-this-store + release-by-`find_valid` + exact patch-object binding + single-use + non-expiry + context match.
- FAIL-CLOSED: missing/malformed/expired/wrong/replayed/forged -> DENY at approval stage and/or apply boundary.
- TEST EVIDENCE: approval_boundary_test.py (48), corpus A13-A20.

## 7.6 Authorization
- WHO CONTROLS: `ApplyAuthorization` (store-backed when the gate is enabled).
- WHAT CAN BE FORGED: duck-typed `approved=True` objects, forged decisions, claimed approval ids, evidence-only metadata, object-substituted patches.
- VALIDATION: typed decision + fingerprint + (store-backed) `decision.approval_id` + `ApprovalStore.authorize_apply(approval_id, patch)`.
- FAIL-CLOSED: all of the above denied; the approval is consumed exactly once at apply.
- TEST EVIDENCE: approval_boundary_test.py MISSION-014 A-O.

## 7.7 Apply
- WHO CONTROLS: `ApplyExecutor`/`FileApplier`.
- WHAT CAN BE FORGED: stale current content, path escape via `..`/absolute/symlink/junction, silently wrong written bytes.
- VALIDATION: scope re-check (`PathPolicy`), exact `old_content` at write, canonical write-through, post-write read-back + bounded restore.
- FAIL-CLOSED: deny before write; mismatch -> restore + FAIL.
- TEST EVIDENCE: patch_integrity_test.py (6), path_security_test.py (31), adversarial A01-A04/A07/A08b/A12b.

## 7.8 Verify
- WHO CONTROLS: `VerificationExecutor` (deterministic; compileall + pytest via non-shell arg lists).
- WHAT CAN BE FORGED: a worker/result claim of verification PASS.
- VALIDATION: PASS only on exit code 0, no timeout/error; verification runs only after a successful apply; `ApplyVerifyResult.success` requires apply AND verification.
- FAIL-CLOSED: apply success is never verification success; verification failure fails the run (retry only if budget).
- TEST EVIDENCE: verification_executor_test.py (15), adversarial A08/A09.

## 7.9 Evidence
- WHO CONTROLS: `WorkerEvidenceRecorder` (dispatches normal Events through `Kernel.dispatch`).
- WHAT CAN BE FORGED: tampered event payloads after dispatch; evidence records claiming authority.
- VALIDATION: hash-chain (previous_hash/current_hash SHA-256, verify from GENESIS); allow-list event factory; secret-safe payloads.
- FAIL-CLOSED: chain break detected by `HashVerifier.verify`; evidence is never an authorization input (MISSION-014 M-test).
- TEST EVIDENCE: worker_evidence_test.py (13), adversarial A11, approval_boundary M.

## 7.10 Recovery
- WHO CONTROLS: `BoundedRecoveryEngine`.
- WHAT CAN BE FORGED: unbounded retry requests (999), duplicate proposals to blind-reapply.
- VALIDATION: `_bounded_max_attempts` clamps to cap 3; retry only on verification FAIL; `_first_duplicate` stops repeats.
- FAIL-CLOSED: no fourth attempt ever; non-verification failures terminal.
- TEST EVIDENCE: recovery_engine_test.py (33), adversarial A10.

---

# 8. SECURITY BOUNDARIES

Full detail: docs/SECURITY_MODEL.md. Summary of implemented boundaries
(all **VERIFIED** by tests unless noted):

- Path scope: canonical containment via `PathPolicy` (resolve + normcase +
  `_within`); traversal (`..`), null bytes, empty scope, symlink/junction
  escape all rejected; enforced at validator AND at write time.
- Patch validation: `modify` action only; exact full-file `old_content`
  match; non-empty change; target exists and is a file.
- Apply: typed `ControllerDecision` with `approved is True` + exact
  fingerprint; store-backed approval verification for HIGH/CRITICAL/UNKNOWN
  (MISSION-014).
- Write integrity: read-back of written bytes == approved `new_content`;
  mismatch -> bounded restore + FAIL.
- Verification: deterministic, shell-free; apply success != verification
  success.
- Retry: hard cap 3; no recursion; duplicate fingerprints stop.
- Risk: system-derived; LLM advisory only raises; UNKNOWN -> DENY.
- Human approval: fingerprint/path/action/risk/attempt/expiry-bound,
  single-use at lookup and at apply; fail-closed on
  missing/malformed/expired/wrong/replayed/forged; interactive CLI UX
  (MISSION-017) routes explicit human decisions into the store and is
  never itself an authority.
- Default runtime: proposal-only (apply/recovery opt-in via
  `build_recovery_agent()` / `agent_run.py --recovery`).
- Risk gate: DEFAULT OFF (D-021/D-022); explicit opt-in requires both
  `risk_engine` and `risk_policy`.

Known boundary limitations (VERIFIED, documented in SECURITY_MODEL.md):
- Write is not atomic against an adversarial concurrent writer; restore is
  best-effort.
- Symlink behavior is UNKNOWN on OSes without symlink privileges (junction
  variants pass on Windows).

---

# 9. AUTHORIZATION MODEL (post MISSION-014)

This section is verified against source and tests, not copied from a
report. The model (source chain):

```
Controller.approve(patch, validation, approval=consumed_approval)
  -> ControllerDecision(approved=True, patch_fingerprint=..., approval_id=...)
       controller.py; controller_decision.py
   -> ApplyAuthorization.authorize(decision, patch)
       apply_authorization.py
       - isinstance(decision, ControllerDecision)        (fake object rejected)
       - decision.approved is True
       - decision.patch_fingerprint == patch.fingerprint()
       - risk = RiskEngine.classify(patch)               (recomputed, not from decision)
       - if risk in {LOW, MEDIUM}:                        (MISSION-018A SAFE content)
             authorize on the typed-decision + fingerprint contract
       - HIGH/CRITICAL/UNKNOWN (MISSION-018B):
             if approval_store is None -> DENY            (no authority => no apply)
             decision.approval_id non-empty
             ApprovalStore.authorize_apply(approval_id, patch)
  -> ApprovalStore.authorize_apply(approval_id, patch)
       approval_store.py
       - approval_id str non-empty
       - approval_id in self._approvals                  (granted by THIS store)
       - approval_id in self._consumed                   (released by find_valid)
       - approval_id not in self._applied                (single-use at apply)
       - self._bindings[approval_id] is patch            (exact object identity)
       - not expired
       - fingerprint/path/action match the approval
       - mark _applied (consumed exactly once)
```

Every binding the mission requires is enforced:

| Binding | Enforced by | Test |
|---------|-------------|------|
| approval_id binding | `ControllerDecision.approval_id` + `authorize_apply` | test_b/test_d |
| exact PatchProposal object binding | `_bindings[approval_id] is patch` | test_n |
| patch fingerprint | `decision.patch_fingerprint` + `authorize_apply` | test_e |
| path | `authorize_apply` + `_approval_is_valid` | test_f |
| action | `authorize_apply` + `_approval_is_valid` | test_g |
| risk context | `find_valid(risk_level=...)` + `_approval_is_valid` + boundary recompute | test_h |
| attempt context | `find_valid(attempt=...)` + `_approval_is_valid` | test_i |
| approval identity | grant-by-this-store + released-by-`find_valid` | test_c/c2 |
| expiry | `find_valid` skip + `authorize_apply` | test_k |
| single-use find_valid | `_consumed` set | test_approval_store_replayed_approval_is_consumed |
| single-use authorize_apply | `_applied` set | test_j |
| forged ControllerDecision rejection | `isinstance` + approval_id requirement | test_b |
| fake object rejection | `isinstance(decision, ControllerDecision)` | test_a |
| agent-claimed approval rejection | store grant lookup | test_c |
| evidence-only authority rejection | store never consults evidence | test_m |
| lower-level bypass rejection | store-backed authorize path | test_o |
| replay rejection | `_consumed` + `_applied` | test_j, A13 |
| substitution rejection | fingerprint/path/action + object identity | test_e/f/g/n, A14/A15/A18/A19 |

Verification entry points: `tests/approval_boundary_test.py`
(`test_a_*`..`test_o_*`), `tests/security/adversarial_corpus_test.py`
(A13-A20), `tests/controller_decision_test.py`. **VERIFIED** â€” 48 approval
tests pass.

---

# 10. RISK MODEL

- `RiskLevel` ordering UNKNOWN(0) < LOW(1) < MEDIUM(2) < HIGH(3) <
  CRITICAL(4); most restrictive wins (`risk_level.py`).
- `RiskEngine.classify` derives level from signals: action
  (destructive=>CRITICAL, non-modify=>HIGH), security-sensitive path=>
  HIGH, privilege-boundary path=>CRITICAL, production-config=>HIGH,
  secret-file suffix/name=>CRITICAL, executable-source=>MEDIUM, large
  change (>500 chars)=>HIGH, PEM block=>CRITICAL, secret-like assignment=>
  HIGH; missing/malformed action=>UNKNOWN (fail-closed bug fixed in
  MISSION-011). MISSION-018A adds fail-closed content classification:
  content is SAFE (plain; LOW/MEDIUM baseline), SUSPICIOUS (credential-like
  material -> HIGH, approval required) or OPAQUE (control characters ->
  UNKNOWN -> DENY); `not detected` is never treated as `safe`. Structural
  heuristics cover JSON/YAML/TOML/dotenv credential keys, bare token
  prefixes, base64/encoded material, URLs with userinfo, shell credential
  flags, env secret references and auth headers/Bearer; path signals add
  backup/temp suffixes, hidden credential files, credential directories
  and production-env naming. Trivial assignments (`self.token = None`)
  stay benign (`risk_engine.py`).
- Advisory LLM risk only raises the level; invalid advisory dropped;
  advisory UNKNOWN not applied; confidence recorded only when numeric and
  never a decision input.
- `RiskPolicy` maps: missing/malformed=>DENY; UNKNOWN=>DENY (never
  auto-approvable); LOW=>auto (max_attempts 3); MEDIUM=>auto (2);
  HIGH/CRITICAL=>human approval required (max_attempts 1, never auto-applied);
  verification_depth=`compile+tests` for all non-deny levels (`risk_policy.py`).
  LOW/MEDIUM auto-apply assumption (MISSION-018A): safe only because
  SUSPICIOUS content is always elevated to HIGH and OPAQUE is DENIED.
- The gate is DEFAULT OFF (needs both `risk_engine` and `risk_policy`;
  D-021/D-022). **VERIFIED** â€” risk tests (MISSION-011/018A);
  risk_pipeline_test.py; corpus A37-A50.

---

# 11. APPROVAL MODEL

- `Approval`: frozen; bound to patch_fingerprint, path, action, risk_level
  (HIGH/CRITICAL only), attempt, authorizer, created_at, expires_at;
  construction raises on malformed values (`approval.py`).
- `ApprovalStore.grant(...)` persists + records a
  `WorkerHumanApprovalGranted` evidence event.
- `find_valid(fingerprint, path, action, risk_level, attempt, patch=None)`:
  incomplete context fails closed; returns first unexpired unconsumed
  matching approval; consumes it; binds exact patch object when supplied.
- `authorize_apply(approval_id, patch)`: apply-boundary single-use
  consumption (Section 9).
- Pipeline `_approval_is_valid` re-validates the returned object (typed +
  full binding + non-expiry) as defense in depth.
- Single-use at lookup and at apply; replay impossible. **VERIFIED** â€”
  approval_boundary_test.py (48); corpus A13-A20.
- **Interactive CLI UX (MISSION-017):** `ConsoleApprovalGateway` +
  `approval_console.py` render a `PendingApprovalRequest` (fingerprint,
  path, action, risk level + context, attempt, expiry, authorizer,
  evidence reference) and route an explicit human approve/deny into
  `store.grant`. The pipeline consults the gateway only when no valid
  stored approval exists; the grant is then re-consumed via `find_valid`
  (object-identity binding + single-use preserved). Displayed == granted
  == applied by construction (all derived from the same patch object +
  system risk); a risk downgrade is refused by the gateway. Agent-controlled
  approval metadata is never consulted. **VERIFIED** â€”
  tests/approval_console_test.py (23), corpus A31-A36.

---

# 12. APPLY / VERIFY MODEL

- Apply: `ApplyExecutor.apply` -> `ApplyAuthorization.authorize` ->
  `FileApplier.apply` (scope re-check, exact old_content, canonical write,
  read-back + restore). Deny => `ApplyResult(success=False)`, no write.
- Verify: `ApplyVerifyPipeline.execute` runs verification only after a
  successful apply; `ApplyVerifyResult.success` requires apply AND
  verification pass. Verification = `compileall -q` then `pytest -q`
  (arg lists, `shell=False`); depth switch `compile` vs `compile+tests`
  (`apply_verify_pipeline.py`, `verification_executor.py`).
- Apply success is never verification success (D-005). **VERIFIED** â€”
  apply_verify_pipeline_test.py (9), adversarial A08/A09.

---

# 13. EVIDENCE / AUDIT MODEL

- `EventStore` append-only JSONL; each record: event_id, event_type,
  payload, sequence, previous_hash, current_hash (SHA-256 over record)
  (`event_store.py`, `hash_chain.py`).
- `HashVerifier.verify` recomputes from GENESIS; any mutation breaks the
  chain (adversarial A11).
- `WorkerEvidenceRecorder` dispatches normal Events through `Kernel.dispatch`
  (sequence/hash/snapshot/replay all apply) and mirrors into in-memory
  `DecisionTrace` (`worker_evidence_recorder.py`, `decision_trace.py`).
- Payload contract: fingerprints and status only â€” never patch
  old/new content, verification stdout/stderr, or secrets (D-013).
- 14 worker event types incl. `WorkerHumanApprovalGranted`
  (`worker_events.py`).
- Evidence records authority/decisions but is never an authorization input
  (MISSION-014 test_m). **VERIFIED** â€” worker_evidence_test.py (13),
  adversarial A11, approval_boundary M.

---

# 14. RECOVERY / RETRY MODEL

- `BoundedRecoveryEngine.execute`: iterative for-loop over a single attempt
  counter; hard cap `MAX_ATTEMPTS_CAP = 3` (`_bounded_max_attempts` clamps
  caller values); never recurses.
- Retry ONLY on verification FAIL; validator/controller/apply failures
  terminal; worker/pipeline exceptions terminal.
- Duplicate proposal fingerprints stop retries (no blind reapply).
- `RecoveryAttempt` (AttemptStatus SUCCESS/FAILED/BLOCKED/ERROR) and
  `RecoveryResult` are immutable, append-only evidence contracts.
- Recovery passes `attempt=attempt_number` into the pipeline so approval
  attempt binding works (MISSION-012).
- **Authorization (MISSION-018B):** the apply boundary recomputes risk and
  DENIES every HIGH/CRITICAL/UNKNOWN apply without a store-verified,
  single-use approval; a missing approval store is itself a denial, so
  RECOVERY (and any gate-off assembly) can never mutate such patches. Each
  retry is an independent PatchProposal with its own risk + approval
  evaluation; old approvals never inherit; the retry budget never
  substitutes for human authorization. `agent_run.py --recovery` wires the
  risk gate + approval store + ledger (pre-authorized autonomous retry);
  `--governed` additionally wires the interactive console gateway.
  **VERIFIED** — adversarial corpus A51-A65.
- Active only via `build_recovery_agent()` / `agent_run.py --recovery`;
  the default runtime is proposal-only. **VERIFIED** — recovery_engine_test.py
  (33), adversarial A10/A51-A65.

---

# 15. ADVERSARIAL SECURITY MODEL

`tests/security/adversarial_corpus_test.py`: 25 test functions / 23
records A01-A65, summary-gated (the final summary test fails the suite if
any recorded attack regressed). Records:

| ID | Attack | Result |
|----|--------|--------|
| A01 | Path traversal (`..`) | DENY, no write |
| A02 | Absolute path outside scope | DENY, no write |
| A03/A03b | Symlink / junction escape | DENY, outside file untouched |
| A04 | Unauthorized path | DENY |
| A05/A05b | Unauthorized action / allowed_actions | DENY |
| A06 | Duplicate old_text | REJECT, no proposal |
| A07 | Stale patch / concurrent modification | DENY, content intact |
| A08/A08b | Apply != verify; corrupted write | FAIL + restore |
| A09 | Verification forgery | verification only from executor |
| A10 | Retry budget (999 requested) | hard cap 3 |
| A11 | Evidence tampering after dispatch | hash chain detects |
| A12/A12b | Fingerprint boundary / prefix confusion | DENY |
| A13 | Approval replay | first ALLOW, second DENY |
| A14 | Approval substitution (approve A, replay for B) | DENY |
| A15 | Risk-context substitution (HIGH approval for CRITICAL flow) | DENY |
| A16 | Forged dict approval metadata (hostile store) | DENY |
| A17 | Expired / stale approval | DENY |
| A18 | Attempt substitution (attempt-1 approval at attempt 2) | DENY |
| A19 | Path substitution (typed Approval, different path) | DENY |
| A20 | Approval-gate bypass (no authority + proposal claims) | DENY |

MISSION-014 adds 17 deterministic boundary tests (A-O) in
`tests/approval_boundary_test.py` (Section 9). **VERIFIED** â€” corpus
24 passed, 1 symlink skip.

---

# 16. TEST ARCHITECTURE

Authoritative run (2026-08-13): **648 passed, 10 skipped**. Per module
(collected counts, VERIFIED by `pytest --collect-only`):

| Module | Count |
|--------|-------|
| tests/approval_boundary_test.py | 48 |
| tests/structured_analysis_test.py | 41 |
| tests/security/adversarial_corpus_test.py | 76 (A01-A72) |
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
| tests/worker_action_pipeline_test.py | 11 |
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
| tests/llm_provider_integration_test.py | 2 (gated, skipped in normal suite) |
| tests/planner_contract_test.py | 1 |
| recovery_test.py (root) | 1 |

- 10 skipped: 3 gated `live_llm` tests + 7 symlink-dependent tests (junction
  variants pass on Windows).
- Script-style files not collected by pytest: calculator_test.py,
  context_test.py, decision_trace_test.py, hash_test.py, loop_test.py,
  memory_event_test.py, memory_events_test.py, memory_test.py,
  planner_test.py, read_after_test.py, registry_test.py, replay_test.py,
  snapshot_test.py, strategy_dispatcher_test.py, tool_executor_test.py,
  test_run.py.
- Empty test subpackages: `tests/chaos/`, `tests/integration/`,
  `tests/property/`, `tests/unit/`.
- Gated live test: `$env:RUN_LIVE_LLM="1"; python -m pytest -m live_llm
  tests/llm_provider_integration_test.py -q` (never runs in the normal
  suite; no API cost).

Command conventions (documented and used by every mission):
`.venv\Scripts\python.exe -m pytest -q`, `.venv\Scripts\python.exe -m
compileall -q simulation tests`, `git diff --check`.

---

# 17. GIT / BRANCH / COMMIT MODEL

- Branch: `worker-action-pipeline` (14 commits ahead of `main`; `main` has
  no commits absent from this branch â€” VERIFIED `git log main..HEAD`).
- HEAD: `f94c82b`; latest tag `v0.5.0` predates the worker-action-pipeline
  work (4 tags: v0.1.0-alpha, v0.3.0, v0.4.0, v0.5.0).
- 72 commits total. Pre-numbered Sprint history (Sprint-1..Sprint-18) built
  the core (event sourcing, replay, hash chain, memory, tools, executors).
- Numbered missions (MISSION-003..014) hardened worker action, evidence,
  risk and approval.
- MISSION-012/013/014 close-outs are **uncommitted working-tree evidence**
  per sprint rules (no commit / no push).
- Working tree also carries MISSION-012/013 doc changes (`docs/*`) and
  test updates (`tests/risk_pipeline_test.py`,
  `tests/security/adversarial_corpus_test.py`).
- Remote: `origin` = https://github.com/khalikinisoran-jpg/olay-kaynak-platformu.git.
- `.gitignore` excludes `.env`, `.venv/`, `data/`, `__pycache__/`, `*.pyc`.
- Tracked junk: `git` (0 bytes), `kernel.txt`, and tracked `.pyc` artifacts
  under `simulation/domain/__pycache__/` and
  `simulation/security/__pycache__/` (documented hygiene debt).

Key commits for the security/worker work:

```
64127ef Add controlled worker patch apply pipeline
fc75847 Harden worker patch authorization
da72dfd Add LLM-driven worker patch analysis
42706da Isolate worker contract tests from LLM
4809b2b Enforce fail-closed patch path scope
b9ddb74 Harden patch path security
9ef829a Isolate worker read-side path scope
9df8390 Add verification executor
5c475b6 Enable worker runtime dispatch
609b89c Enforce fail-closed worker runtime
f40ceab Integrate explicit worker action pipeline
90400c9 Add bounded verification recovery
ea9b2ab Add worker decision trace evidence
18a1f6c Harden OpenRouter provider + gated LLM integration test
93a9d4b Security baseline audit and hardening
f5d1fbc Harden patch integrity boundary
2249a04 Harden controller decision contract
27effbf Add adversarial security test corpus
9b5c21e Synchronize sprint project state
fc8f593 Add structured worker analysis result contract
96ed72d Integrate risk-aware worker action pipeline
f94c82b Close MISSION-011 and synchronize project knowledge
```

---

# 18. MISSION HISTORY

Statuses derived from `docs/MISSION_LOG.md`, `docs/MISSION_STATUS.md`,
git history and the passing suites. "LAST VERIFIED" is the state at
2026-08-12.

| Mission | Title | Status | Implementation | Evidence / Tests | Related commits | Remaining work |
|---------|-------|--------|----------------|------------------|-----------------|----------------|
| (historic x8) | Fail-Closed Patch Path Scope, Patch Path Security, Worker Read-Side Path Scope, Verification Executor, Worker Runtime Dispatch, Fail-Closed Worker Runtime, Explicit Worker Action Pipeline, Bounded Verification Recovery | IMPLEMENTED / VERIFIED-by-suite | worker_agent, patch_validator, verification_executor, worker_action_pipeline, bounded_recovery_engine | MISSION_LOG records; today's suites cover the behavior | 4809b2b, b9ddb74, 9ef829a, 9df8390, 5c475b6, 609b89c, f40ceab, 90400c9 | â€” |
| (doc) | Architecture Audit / Project State Synchronization; Project State Synchronization; MISSION-009 Sprint State Sync | DONE | docs-only | MISSION_LOG entries | 3966e18, 19c6e85, 9b5c21e | â€” |
| MISSION-003 | Real-LLM Gated Integration Test + Provider Hardening | VERIFIED | OpenRouterProvider hardening (timeout, ProviderError, secret-safe) | llm_provider_test.py (9); live smoke passed | 18a1f6c, 07e70b2 | multi-provider parity |
| MISSION-004 | Worker Decision Trace Evidence | VERIFIED | WorkerEvidenceRecorder + events + pipeline/recovery wiring | worker_evidence_test.py (13) | ea9b2ab, 98b11e1 | DecisionTrace persistence (open) |
| MISSION-005 | Security Baseline Audit | VERIFIED | task.allowed_actions enforcement | worker_read_scope_test.py (16); SECURITY_BASELINE.md | 93a9d4b | â€” |
| MISSION-006 | Patch Integrity Hardening | VERIFIED | PathPolicy.resolve_target + read-back/restore in FileApplier | patch_integrity_test.py (6) | f5d1fbc | atomicity vs concurrent writer (documented) |
| MISSION-007 | Controller Decision Hardening | VERIFIED | typed ValidationResult contract | controller_decision_test.py (13) | 2249a04 | â€” |
| MISSION-008 | Adversarial Security Test Corpus V0.1 | VERIFIED | corpus A01-A12 summary-gated | adversarial_corpus_test.py | 27effbf | later extended by MISSION-013 |
| MISSION-010 | Structured Worker Analysis Result | VERIFIED | AnalysisResult contract; analyzer fail-closed | structured_analysis_test.py (41) | fc8f593 | â€” |
| MISSION-011 | Risk / Policy Engine | VERIFIED / CLOSED | RiskLevel/RiskEngine/RiskPolicy + fail-closed action bug fix + opt-in gate | 83 risk tests (risk_level/engine/policy/pipeline) | 96ed72d (impl), f94c82b (close-out) | gate default-on decision (D-021/D-022) |
| MISSION-012 | Human Approval Boundary | VERIFIED / CLOSED | Approval/ApprovalStore + STAGE_APPROVAL + evidence event | approval_boundary_test.py (started at 31) | working tree | human-approval UX |
| MISSION-013 | Advanced Adversarial Benchmark | VERIFIED / CLOSED | corpus extended A13-A20 | adversarial_corpus_test.py (25 fns) | working tree | concurrency/live-LLM threat categories |
| MISSION-014 | Authorization Boundary Hardening | **VERIFIED / CLOSED** | store-backed ApplyAuthorization; approval_id binding; object-identity binding; authorize_apply single-use; context-fail-closed find_valid | approval_boundary_test.py (48, incl. A-O); full suite 390 passed / 9 skipped | `d347f43` | interactive human-approval UX (**done in MISSION-017**); default-on gate decision |
| MISSION-016 | Chief Engineer Verified-Gap-Closure Sprint | **VERIFIED / CLOSED (committed)** | `--governed` runtime; rollback on verify-FAIL; ApprovalLedger durability; O(1)/locked/fsynced EventStore; snapshot content-hash; verification hardening (timeout/no-tests/pycache-redirect); secret/prompt-injection boundary; lazy provider; risk boundary-matching; corpus A21-A30; CI + pyproject | 465 passed / 10 skipped; corpus 34/1; live-LLM E2E 1 passed (real provider) | `d347f43`, `a8de82e` | Linux/macOS hosted CI run; MISSION-015 |
| MISSION-017 | Overnight Productization & Human Approval Sprint | **IMPLEMENTED / VERIFIED-by-suite** (uncommitted working tree) | interactive CLI approval console (approval_console.py + ConsoleApprovalGateway); runtime-mode tests; corpus A31-A36; CI packaging smoke; approval-lookup benchmark | 521 passed / 10 skipped; corpus 40/1 | working tree (base `a8de82e`) | hosted CI run; default-on gate decision; MISSION-015 |
| MISSION-018A | Risk Boundary Hardening | **IMPLEMENTED / VERIFIED-by-suite** (uncommitted working tree) | RiskEngine SAFE/SUSPICIOUS/OPAQUE fail-closed content classification; path hardening; LOW/MEDIUM security assumption documented; risk-regression corpus; pipeline tests; corpus A37-A50 | 579 passed / 10 skipped; corpus 54/1 | working tree (base `a8de82e`) | hosted CI; default-on gate decision; MISSION-015 |
| MISSION-018B | Recovery Approval Boundary | **IMPLEMENTED / VERIFIED-by-suite** (uncommitted working tree) | ApplyAuthorization store-less HIGH/CRITICAL/UNKNOWN => DENY; agent_run --recovery wired to risk+store+ledger (no interactive gateway); corpus A51-A65 | 594 passed / 10 skipped; corpus 69/1 | working tree (base `a8de82e`) | hosted CI; default-on gate decision; MISSION-015 |
| MISSION-019 | Governance Boundary Consolidation & Crash-Consistency | **IMPLEMENTED / VERIFIED-by-suite** (uncommitted working tree) | GovernanceEvaluator single authority (D-031); ApplyOutcomeJournal + detect-only startup reconciliation (D-032); atomic snapshots (D-033); Kernel reducer-failure semantics; retry-evidence redaction (D-034); corpus A66-A72 | 648 passed / 10 skipped; corpus 76/1 | working tree (base `a8de82e`) | hosted CI; default-on gate decision; MISSION-015; orphan auto-repair decision |
| MISSION-015 | Productization Readiness Assessment | PLANNED | â€” | â€” | â€” | â€” |

---

# 19. CURRENT LIVE STATE

- Branch `worker-action-pipeline` @ `a8de82e`; 17 commits ahead of `main`
  (VERIFIED `git log main..HEAD`).
- Working tree: MISSION-017 sprint changes uncommitted (interactive approval
  console, runtime-mode tests, corpus A31-A36, CI packaging smoke,
  approval-lookup benchmark, doc sync).
- Test suite: **521 passed / 10 skipped** (2026-08-13); adversarial corpus
  **40 passed / 1 skipped**; `compileall` exit 0; `git diff --check` clean;
  gated live-LLM E2E **1 passed** (real provider, 2026-08-12).
- Untracked: `simulation/agent/approval/approval_console.py`,
  `tests/approval_console_test.py`, `tests/runtime_mode_test.py`,
  `benchmarks/approval_lookup_benchmark.py`.
- `.env` present locally (OPENROUTER_API_KEY, untracked/gitignored).
- CI workflow (`.github/workflows/ci.yml`, ubuntu + windows, pytest +
  compileall + corpus + diff-check + packaging smoke); `pyproject.toml`
  packaging metadata (`pip install -e .` verified locally 2026-08-13).

---

# 20. KNOWN LIMITATIONS

VERIFIED where not marked:

1. The human-approval UX is CLI/synchronous: `ConsoleApprovalGateway`
   blocks the governed run until the operator types approve/deny (EOF
   fails closed). No async/web approval channel.
2. Governed apply / recovery / risk gate are explicit opt-in
   (`--governed`, `--recovery`); the shipped default runtime stays
   proposal-only (D-021/D-022/D-028).
3. No production/deployment story: no hosted service, no multi-user model,
   no production metrics. CI and packaging metadata exist but no CI run has
   been exercised externally (the MISSION-017 packaging smoke step included).
4. Single-process, single-user CLI only. EventStore append is serialized
   per-instance; multi-process writers on one store file are unsupported.
5. Approval durability requires a wired `ApprovalLedger`; without a ledger
   the store is in-memory (tests use both modes). Object-identity binding is
   in-memory by nature and re-bound on the next `find_valid`.
6. Rollback on verification failure is provided by the real `ApplyExecutor`;
   a custom executor without a `rollback` method leaves the failed state in
   place (documented in `ApplyVerifyPipeline`).
7. Live-LLM end-to-end (apply/verify/recovery) is covered by a gated test
   (`tests/live_llm_e2e_test.py`) that passed once with a real provider; it
   never runs in the normal suite and exercises the MEDIUM-risk path only.
8. Symlink behavior untested on OSes without symlink privileges (junction
   variants cover Windows); CI now runs the suite on Linux/Windows.
9. Write is atomic via tempfile+replace, but not protected against a
   concurrent adversarial writer of the same file; restore on read-back
   mismatch is best-effort.
10. Secret redaction is a heuristic defense-in-depth, not a guarantee; the
    analyzer is never shown whole secret files but a missed pattern could
    still leak. Prompt-injection resistance is a mitigation, not a proof.
11. `weather` planner branch removed (was unroutable); "hava" prompts route
    to the LLM strategy.
12. Repository hygiene: tracked junk staged for removal (`git` 0 bytes,
    `kernel.txt`, tracked `.pyc`); docs drift in README/CHANGELOG/
    PROJECT_CONTEXT remains.
13. Duplicate snapshot implementations and legacy
    `persistence/recovery.py`/`event_store_backup.py` overlap remain
    (not removed without proof of dead code).
14. `WorkerExecutor` hardcodes `task_id="worker-task"` and
    `allowed_actions=("read","inspect","propose")`.

---

# 21. UNKNOWN / UNPROVEN ITEMS

Keep these unresolved â€” do not write them as solved:

- Live-LLM end-to-end apply/verify/recovery behavior across providers and
  environments (one gated run passed; not a guarantee). HIGH/CRITICAL live
  path with the interactive approval console is NOT covered by any gated
  test.
- Concurrency / multi-agent behavior; multi-process writes to one store file.
- Whether the risk gate becomes default-on in a productized assembly
  (productization decision, D-021/D-022/D-028; a CLI approval UX now
  exists, so the decision is no longer blocked on implementation).
- Async/web human-approval channel (the MISSION-017 CLI is synchronous).
- Symlink-dependent security behavior outside this Windows environment.
- Whether the MISSION-017 CI packaging smoke step passes on a hosted runner
  (verified locally only).
- Production/deployment behavior, real load/IO performance (the benchmark
  is a local sanity number, not a production measurement).
- Market/external validation of product claims; competitor comparison.
- Intended scope of MISSION-015.
- Whether DecisionTrace should become persistent (currently in-memory).

---

# 22. NEXT 3-5 ACTIONS

Ranked by risk reduction vs effort (INFERRED recommendation; MISSION-016
is committed, MISSION-017 is implemented but uncommitted):

1. **Commit / push the MISSION-016 + MISSION-017 sprint** (uncommitted by
   sprint rule), then run the new CI (incl. packaging smoke) on a hosted
   runner to close the symlink and Linux/macOS coverage gap.
2. **Decide the default-on gate** â€” the interactive human-approval UX now
   exists (MISSION-017), so the D-021/D-022 gate default-on decision is a
   pure productization choice with no missing implementation dependency.
3. **Synchronize remaining stale docs** (README, CHANGELOG, PROJECT_CONTEXT,
   docs/ROADMAP) with the verified baseline.
4. **MISSION-015 Productization Readiness Assessment** (planned).
5. **Finish repository hygiene** (legacy `persistence/recovery.py`,
   `event_store_backup.py`, duplicate snapshots, `services/` overlap) with
   dead-code evidence per component.

---

# 23. QUICK START FOR FUTURE ENGINEERS / AGENTS

1. Read this file, then docs/PROJECT_STATE.md, docs/SECURITY_MODEL.md and
   docs/ARCHITECTURE.md.
2. Confirm the baseline: `.venv\Scripts\python.exe -m pytest -q` (expect
   521 passed / 10 skipped at the MISSION-017 checkpoint).
3. Understand the runtime flow (Section 5) before touching code.
4. The security critical path is: WorkerResult -> validation -> risk ->
   approval (ApprovalStore; optional CLI gateway) -> controller ->
   ApplyAuthorization (store-backed) -> FileApplier -> verification ->
   evidence -> recovery. The apply authorization boundary (Section 9) is the
   narrowest trust enforcement point; change it only with the approval model
   in mind.
5. Testing conventions: use `tmp_path` fixtures, keep tests deterministic
   and in the canonical files (extend existing test modules rather than
   creating parallel suites). Gated `live_llm` tests never run in the
   normal suite.
6. After any mission: update PROJECT_MASTER (this file) + the canonical
   docs (Section 4), run `pytest -q`, `compileall -q simulation tests`,
   `git diff --check`, and record the result. Do not commit/push unless
   explicitly instructed.

---

## Canonical Source Relationship

- PROJECT_STATE â€” docs/PROJECT_STATE.md (live state, test counts, git state)
- ARCHITECTURE â€” docs/ARCHITECTURE.md (component architecture)
- SECURITY_MODEL â€” docs/SECURITY_MODEL.md (per-claim verified security model)
- MISSION_STATUS â€” docs/MISSION_STATUS.md (mission-by-mission status)
- MISSION_LOG â€” docs/MISSION_LOG.md (append-only mission completion records)
- DECISION_LOG â€” docs/DECISION_LOG.md (D-001..D-023)
- PROJECT_KNOWLEDGE_AUDIT â€” docs/PROJECT_KNOWLEDGE_AUDIT.md (maturity/gaps audit)
- ROADMAP â€” docs/ROADMAP.md (phased product roadmap; note stale vs code)

PROJECT_MASTER is an index/map of these canonical sources; it does not
replace them. If a claim in PROJECT_MASTER disagrees with source code,
trust the source code.
