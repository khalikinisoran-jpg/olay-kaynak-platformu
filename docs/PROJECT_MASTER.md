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

- **VERIFIED** — confirmed by source code, passing tests, and/or commit
  history at the time of writing.
- **INFERRED** — reasoned from code/tests/history but not directly
  asserted by a single test.
- **UNKNOWN** — cannot be determined from repository evidence.

Source of truth order: Git history > source code > tests > docs. When this
document contradicts code, trust the code.

**STALE DATA POLICY:** if source code changes, any related claim in this
document may become stale. Refresh PROJECT_MASTER at every mission
close-out or after a significant architectural change. Cross-reference the
canonical docs (Section 4) rather than duplicating their full content.

---

# 1. BOOTSTRAP (read this first)

| Field | Value | Class |
|-------|-------|-------|
| CURRENT DATE | 2026-08-12 | VERIFIED |
| CURRENT BRANCH | `worker-action-pipeline` | VERIFIED (`git branch --show-current`) |
| CURRENT HEAD | `f94c82b8d4fadf14d987f493a79240e739321713` (`f94c82b`, "Close MISSION-011 and synchronize project knowledge") | VERIFIED (`git rev-parse HEAD`) |
| WORKTREE STATE | MISSION-012/013/014 close-out changes **uncommitted**: `simulation/agent/approval/` (new), `tests/approval_boundary_test.py` (new), plus modified apply-authorization / controller / pipeline / recovery / risk-test files and docs | VERIFIED (`git status --short`) |
| CURRENT MISSION | none active — MISSION-014 **VERIFIED / CLOSED**; MISSION-015 PLANNED | VERIFIED (docs/MISSION_STATUS.md) |
| LAST VERIFIED TEST RESULT | full suite **390 passed / 9 skipped**; focused approval boundary **48 passed**; approval + adversarial **72 passed / 1 skipped**; `compileall` exit 0; `git diff --check` clean (LF/CRLF warnings only) | VERIFIED (2026-08-12 run) |
| COMPLETED MISSIONS | 8 historic + 3 doc-sync + MISSION-003,004,005,006,007,008,009,010,011,012,013,014 | VERIFIED (Section 18) |
| ACTIVE MISSIONS | none open; MISSION-015 (Productization Readiness Assessment) PLANNED | VERIFIED |
| OPEN SECURITY RISKS | no interactive human-approval UX; live-LLM end-to-end untested; concurrency/multi-agent untested; symlink behavior beyond Windows junction coverage untested; risk gate intentionally DEFAULT OFF | VERIFIED (Section 20) |
| UNKNOWN ITEMS | see Section 21 | — |
| NEXT 3-5 PRIORITIES | 1) human-approval UX, 2) sync stale docs, 3) fix `weather` routing gap, 4) repo hygiene, 5) MISSION-015 productization readiness | INFERRED (Section 22) |

Quick orientation: the repository is an **event-sourced AI runtime
prototype**. A worker (optionally LLM-driven) proposes file modifications;
deterministic gates (validator -> controller -> apply -> verify) decide;
every decision becomes a hash-chained event. Apply/recovery are **opt-in
only**; the default runtime is proposal-only.

---

# 2. PROJECT PURPOSE

Build an event-sourced AI runtime in which every meaningful AI action
becomes an immutable, hash-chained event, so AI decisions can be replayed,
recovered, verified and audited, and constrained by deterministic system
controls. **VERIFIED** — docs/FOUNDING_PRINCIPLES.md, docs/PHILOSOPHY.md,
VISION.md, README.md; the full replay/verify/evidence machinery exists in
code (Section 4).

The product claim "trustworthy AI through Event Sourcing, Replay and
Verification" is the stated direction. **VERIFIED as project intent**;
external validation of the claim is **UNKNOWN** (no market research,
customer interviews or production deployment exist — docs/PRODUCT_POSITIONING.md).

---

# 3. PRODUCT DEFINITION

What actually exists (all **VERIFIED** from code/tests):

- An append-only, SHA-256 hash-chained event store with deterministic
  replay and snapshot recovery (`simulation/persistence/event_store.py`,
  `simulation/recovery/recovery_engine.py`, `simulation/replay/replay_engine.py`).
- A CLI chat runtime (`agent_run.py`) routing input through a Planner and a
  StrategyDispatcher of executors (calculator, memory store/recall, LLM,
  worker).
- A worker agent that reads in-scope files and produces **patch proposals**
  only; it never applies (optionally via real LLM OpenRouter/DeepSeek,
  gated tests).
- A deterministic apply/verify pipeline with bounded recovery — active
  only when explicitly assembled (`build_recovery_agent()` or
  `agent_run.py --recovery`).
- A documented security model with executable adversarial tests
  (`tests/security/adversarial_corpus_test.py`, A01-A20).
- A system-derived risk layer (`RiskEngine`/`RiskPolicy`/`RiskLevel`) and a
  fingerprint-bound, single-use human-approval boundary
  (`Approval`/`ApprovalStore`) hardened at the apply authorization boundary
  (MISSION-011/012/014).

What it is **not** (VERIFIED): a productized, packaged, deployed or
externally validated platform. No production configuration, CI, packaging,
API service, multi-user story, benchmarks or concurrency tests exist.

Unproven product/marketing claims (differentiators like "enterprise-grade",
"provider-agnostic beyond OpenRouter", "faster/safer than existing agent
frameworks") are **UNKNOWN/UNVERIFIED** — docs/PRODUCT_POSITIONING.md
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
  security/      PathPolicy, HashChain, HashVerifier, RiskLevel, RiskEngine, RiskPolicy
  decision/      DecisionTrace (in-memory)
  loop/          LoopEngine
  planner/       Planner
  context/       ContextBuilder
  memory/        MemoryService + MemoryEvents
  tools/         BaseTool, Registry, Calculator
  llm/           BaseProvider, OpenRouterProvider, ProviderFactory
  agent/
    agent.py            Agent runtime (chat, dispatches worker/recovery/pipeline)
    strategy_dispatcher.py
    executors/          calculator, memory_store, memory_recall, llm, worker
    worker/             WorkerAgent, WorkerTask, WorkerResult, PatchProposal,
                        PatchValidator, PatchGenerator, LLMCodeAnalyzer,
                        AnalysisResult, ValidationResult, WorkerPolicy
    controller/         Controller, ControllerDecision
    approval/           Approval, ApprovalStore  (MISSION-012/014)
    apply/              ApplyAuthorization, ApplyExecutor, FileApplier, ApplyResult
    verify/             VerificationExecutor, CommandRunner, VerificationResult
    pipeline/           WorkerActionPipeline, ApplyVerifyPipeline, ApplyVerifyResult
    recovery/           BoundedRecoveryEngine, RecoveryAttempt, RecoveryResult, recovery_assembly
    evidence/           WorkerEventType, build_worker_event, WorkerEvidenceRecorder
  domain/               legacy domain models (worker.py, task.py, enums.py)
  services/             legacy tool_executor/runtime_service (overlap with agent/executors/)
agent_run.py            CLI entry point (default proposal-only; --recovery opt-in)
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
- SECURITY ROLE: identity anchor — the fingerprint binds validation/risk/approval/decision/apply
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
- PURPOSE: Executable threat-model benchmark (A01-A20), summary-gated.
- SOURCE: `tests/security/adversarial_corpus_test.py`
- SYMBOLS: `Corpus`, `CorpusRecord`, `test_a01...test_a20`, `test_corpus_summary`
- SECURITY ROLE: regression guard — the summary test fails the suite if any recorded attack regressed
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
  missing/malformed/expired/wrong/replayed/forged.
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
       - if store-backed:
           risk = RiskEngine.classify(patch)             (recomputed, not from decision)
           if risk in {HIGH, CRITICAL, UNKNOWN}:
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
(A13-A20), `tests/controller_decision_test.py`. **VERIFIED** — 48 approval
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
  MISSION-011) (`risk_engine.py`).
- Advisory LLM risk only raises the level; invalid advisory dropped;
  advisory UNKNOWN not applied; confidence recorded only when numeric and
  never a decision input.
- `RiskPolicy` maps: missing/malformed=>DENY; UNKNOWN=>DENY (never
  auto-approvable); LOW=>auto (max_attempts 3); MEDIUM=>auto (2);
  HIGH/CRITICAL=>human approval required (max_attempts 1, never auto-applied);
  verification_depth=`compile+tests` for all non-deny levels (`risk_policy.py`).
- The gate is DEFAULT OFF (needs both `risk_engine` and `risk_policy`;
  D-021/D-022). **VERIFIED** — 83 risk tests; risk_pipeline_test.py.

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
- Single-use at lookup and at apply; replay impossible. **VERIFIED** —
  approval_boundary_test.py (48); corpus A13-A20.

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
- Apply success is never verification success (D-005). **VERIFIED** —
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
- Payload contract: fingerprints and status only — never patch
  old/new content, verification stdout/stderr, or secrets (D-013).
- 14 worker event types incl. `WorkerHumanApprovalGranted`
  (`worker_events.py`).
- Evidence records authority/decisions but is never an authorization input
  (MISSION-014 test_m). **VERIFIED** — worker_evidence_test.py (13),
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
- Active only via `build_recovery_agent()` / `agent_run.py --recovery`;
  the default runtime is proposal-only. **VERIFIED** — recovery_engine_test.py
  (33), adversarial A10.

---

# 15. ADVERSARIAL SECURITY MODEL

`tests/security/adversarial_corpus_test.py`: 25 test functions / 23
records A01-A20, summary-gated (the final summary test fails the suite if
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
`tests/approval_boundary_test.py` (Section 9). **VERIFIED** — corpus
24 passed, 1 symlink skip.

---

# 16. TEST ARCHITECTURE

Authoritative run (2026-08-12): **390 passed, 9 skipped**. Per module
(collected counts, VERIFIED by `pytest --collect-only`):

| Module | Count |
|--------|-------|
| tests/approval_boundary_test.py | 48 |
| tests/structured_analysis_test.py | 41 |
| tests/recovery_engine_test.py | 33 |
| tests/worker_contract_test.py | 31 |
| tests/security/path_security_test.py | 31 |
| tests/risk_engine_test.py | 30 |
| tests/security/adversarial_corpus_test.py | 25 |
| tests/risk_level_test.py | 20 |
| tests/risk_policy_test.py | 18 |
| tests/security/worker_read_scope_test.py | 16 |
| tests/verification_executor_test.py | 15 |
| tests/risk_pipeline_test.py | 15 |
| tests/worker_evidence_test.py | 13 |
| tests/controller_decision_test.py | 13 |
| tests/worker_action_pipeline_test.py | 11 |
| tests/apply_verify_pipeline_test.py | 9 |
| tests/llm_provider_test.py | 9 |
| tests/worker_runtime_test.py | 7 |
| tests/patch_integrity_test.py | 6 |
| tests/worker_runtime_integration_test.py | 4 |
| tests/llm_provider_integration_test.py | 2 (gated, skipped in normal suite) |
| tests/planner_contract_test.py | 1 |
| recovery_test.py (root) | 1 |

- 9 skipped: 2 gated `live_llm` tests + 7 symlink-dependent tests (junction
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
  no commits absent from this branch — VERIFIED `git log main..HEAD`).
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
| (historic x8) | Fail-Closed Patch Path Scope, Patch Path Security, Worker Read-Side Path Scope, Verification Executor, Worker Runtime Dispatch, Fail-Closed Worker Runtime, Explicit Worker Action Pipeline, Bounded Verification Recovery | IMPLEMENTED / VERIFIED-by-suite | worker_agent, patch_validator, verification_executor, worker_action_pipeline, bounded_recovery_engine | MISSION_LOG records; today's suites cover the behavior | 4809b2b, b9ddb74, 9ef829a, 9df8390, 5c475b6, 609b89c, f40ceab, 90400c9 | — |
| (doc) | Architecture Audit / Project State Synchronization; Project State Synchronization; MISSION-009 Sprint State Sync | DONE | docs-only | MISSION_LOG entries | 3966e18, 19c6e85, 9b5c21e | — |
| MISSION-003 | Real-LLM Gated Integration Test + Provider Hardening | VERIFIED | OpenRouterProvider hardening (timeout, ProviderError, secret-safe) | llm_provider_test.py (9); live smoke passed | 18a1f6c, 07e70b2 | multi-provider parity |
| MISSION-004 | Worker Decision Trace Evidence | VERIFIED | WorkerEvidenceRecorder + events + pipeline/recovery wiring | worker_evidence_test.py (13) | ea9b2ab, 98b11e1 | DecisionTrace persistence (open) |
| MISSION-005 | Security Baseline Audit | VERIFIED | task.allowed_actions enforcement | worker_read_scope_test.py (16); SECURITY_BASELINE.md | 93a9d4b | — |
| MISSION-006 | Patch Integrity Hardening | VERIFIED | PathPolicy.resolve_target + read-back/restore in FileApplier | patch_integrity_test.py (6) | f5d1fbc | atomicity vs concurrent writer (documented) |
| MISSION-007 | Controller Decision Hardening | VERIFIED | typed ValidationResult contract | controller_decision_test.py (13) | 2249a04 | — |
| MISSION-008 | Adversarial Security Test Corpus V0.1 | VERIFIED | corpus A01-A12 summary-gated | adversarial_corpus_test.py | 27effbf | later extended by MISSION-013 |
| MISSION-010 | Structured Worker Analysis Result | VERIFIED | AnalysisResult contract; analyzer fail-closed | structured_analysis_test.py (41) | fc8f593 | — |
| MISSION-011 | Risk / Policy Engine | VERIFIED / CLOSED | RiskLevel/RiskEngine/RiskPolicy + fail-closed action bug fix + opt-in gate | 83 risk tests (risk_level/engine/policy/pipeline) | 96ed72d (impl), f94c82b (close-out) | gate default-on decision (D-021/D-022) |
| MISSION-012 | Human Approval Boundary | VERIFIED / CLOSED | Approval/ApprovalStore + STAGE_APPROVAL + evidence event | approval_boundary_test.py (started at 31) | working tree | human-approval UX |
| MISSION-013 | Advanced Adversarial Benchmark | VERIFIED / CLOSED | corpus extended A13-A20 | adversarial_corpus_test.py (25 fns) | working tree | concurrency/live-LLM threat categories |
| MISSION-014 | Authorization Boundary Hardening | **VERIFIED / CLOSED** | store-backed ApplyAuthorization; approval_id binding; object-identity binding; authorize_apply single-use; context-fail-closed find_valid | approval_boundary_test.py (48, incl. A-O); full suite 390 passed / 9 skipped | working tree (f94c82b base) | interactive human-approval UX; default-on gate decision |
| MISSION-015 | Productization Readiness Assessment | PLANNED | — | — | — | — |

---

# 19. CURRENT LIVE STATE

- Branch `worker-action-pipeline` @ `f94c82b`; 14 commits ahead of `main`.
- Working tree: MISSION-012/013/014 close-out uncommitted (approval module,
  apply-authorization hardening, pipeline wiring, tests, docs).
- Test suite: **390 passed / 9 skipped** (2026-08-12); `compileall` exit 0;
  `git diff --check` clean (LF/CRLF warnings only).
- Untracked: `simulation/agent/approval/`, `tests/approval_boundary_test.py`.
- `.env` present locally (OPENROUTER_API_KEY, untracked/gitignored).
- No CI workflows; empty `tests/{chaos,integration,property,unit}`.

---

# 20. KNOWN LIMITATIONS

VERIFIED where not marked:

1. No interactive human-approval UX: `ApprovalStore.grant` is called
   programmatically; HIGH/CRITICAL otherwise fails closed at the approval
   stage (safe, not end-to-end usable).
2. Risk gate and approval/apply hardening are explicit opt-in; the shipped
   assembly stays gate-off (D-021/D-022). Default runtime is proposal-only.
3. No production/deployment story: no CI, packaging, config, metrics.
4. Single-process, single-user CLI only.
5. No concurrency/multi-agent tests; no benchmarks.
6. `weather` planner strategy is unroutable (no registered executor) —
   `planner.py` produces it, `strategy_dispatcher.py` cannot dispatch it.
7. Live-LLM end-to-end (apply/verify/recovery) untested; only proposal-only
   live path covered by gated tests.
8. Symlink behavior untested on OSes without symlink privileges (junction
   variants cover Windows).
9. Write integrity restore is best-effort; no atomicity against adversarial
   concurrent writer.
10. Approval consumption state is in-memory per store instance; durable
    evidence is the `WorkerHumanApprovalGranted` event log.
11. Docs drift: README.md, CHANGELOG.md, docs/PROJECT_CONTEXT.md,
    docs/ROADMAP.md, docs/SESSION_NOTES.md, docs/MILESTONE-2.md describe
    older versions/sprints (README still says v0.1.0-alpha).
12. Repository hygiene: tracked `.pyc` artifacts, junk files (`git`,
    `kernel.txt`), stray Turkish-named empty directories under simulation/.
13. Duplicate snapshot implementations and legacy
    `persistence/recovery.py`/`event_store_backup.py` overlap.
14. `WorkerExecutor` hardcodes `task_id="worker-task"` and
    `allowed_actions=("read","inspect","propose")`.

---

# 21. UNKNOWN / UNPROVEN ITEMS

Keep these unresolved — do not write them as solved:

- Live-LLM end-to-end apply/verify/recovery behavior (only proposal-only
  live path tested).
- Concurrency / multi-agent behavior; concurrent event writes.
- Whether the risk gate becomes default-on in a productized assembly
  (productization decision, D-021/D-022).
- Interactive human-approval UX shape (CLI prompt, approval file, API).
- Symlink-dependent security behavior outside this Windows environment.
- Production/deployment behavior, performance (no benchmarks).
- Market/external validation of product claims; competitor comparison.
- Intended scope of MISSION-015.
- Whether the `weather` planner strategy is intended to work.
- Whether DecisionTrace should become persistent (currently in-memory).

---

# 22. NEXT 3-5 ACTIONS

Ranked by risk reduction vs effort (INFERRED recommendation; current
missions MISSION-011..014 are closed and not re-listed):

1. **Build the human-approval UX** — the boundary exists and is hardened
   (MISSION-012/014); add the interaction that routes a HIGH/CRITICAL
   request to a human and back into `ApprovalStore.grant`. Last piece
   before re-evaluating default-on (D-022).
2. **Synchronize stale docs** (README, CHANGELOG, PROJECT_CONTEXT,
   docs/ROADMAP) with the verified baseline.
3. **Fix the `weather` routing gap** (Planner produces a strategy the
   dispatcher cannot dispatch) or remove the branch; add a
   planner/dispatcher contract test.
4. **Clean repository hygiene** (tracked `.pyc`, junk files, stray
   directories).
5. **MISSION-015 Productization Readiness Assessment** (planned).

---

# 23. QUICK START FOR FUTURE ENGINEERS / AGENTS

1. Read this file, then docs/PROJECT_STATE.md, docs/SECURITY_MODEL.md and
   docs/ARCHITECTURE.md.
2. Confirm the baseline: `.venv\Scripts\python.exe -m pytest -q` (expect
   390 passed / 9 skipped at the MISSION-014 checkpoint).
3. Understand the runtime flow (Section 5) before touching code.
4. The security critical path is: WorkerResult -> validation -> risk ->
   approval (ApprovalStore) -> controller -> ApplyAuthorization
   (store-backed) -> FileApplier -> verification -> evidence -> recovery.
   The apply authorization boundary (Section 9) is the narrowest trust
   enforcement point; change it only with the approval model in mind.
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

- PROJECT_STATE — docs/PROJECT_STATE.md (live state, test counts, git state)
- ARCHITECTURE — docs/ARCHITECTURE.md (component architecture)
- SECURITY_MODEL — docs/SECURITY_MODEL.md (per-claim verified security model)
- MISSION_STATUS — docs/MISSION_STATUS.md (mission-by-mission status)
- MISSION_LOG — docs/MISSION_LOG.md (append-only mission completion records)
- DECISION_LOG — docs/DECISION_LOG.md (D-001..D-023)
- PROJECT_KNOWLEDGE_AUDIT — docs/PROJECT_KNOWLEDGE_AUDIT.md (maturity/gaps audit)
- ROADMAP — docs/ROADMAP.md (phased product roadmap; note stale vs code)

PROJECT_MASTER is an index/map of these canonical sources; it does not
replace them. If a claim in PROJECT_MASTER disagrees with source code,
trust the source code.
