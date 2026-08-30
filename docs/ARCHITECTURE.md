# ARCHITECTURE

> Canonical architecture of what is ACTUALLY implemented on branch
> `worker-action-pipeline` @ `9df6953` (`9df6953b4a51071330d7584f0ed2b569f4ab434b`, current HEAD; 15 commits after the historical P9 FINAL PASS baseline `b2d6da7` `b2d6da7234640e34fa349c067f56e23057053cf2`, 2026-08-25; current local full-suite evidence at `9df6953`: `1278 collected / 1265 passed / 13 skipped / 0 failures` in 329.97s — local Windows run 2026-08-30, NOT hosted CI, NOT a production-correctness proof; historical: full-suite at `d42736d` `1272 collected / 1259 passed / 13 skipped / 0 failures` in 271.43s (2026-08-29); historical P9 FINAL PASS @ `b2d6da7`: `1213 collected / 1200 passed / 13 skipped / 0 failures`, hosted run 32805095789 Ubuntu ~88s / Windows ~182s; foundation `24c72d0` 986 → P7 governed AgentSession → P8 multi-file atomicity → P9 → post-P9 governed ExternalAction additions to 1272; P2.1 CLI / P2.2 task entry / P2.2-FP pending parity / P2.3-A `demo_cli.ps1` conserved as lineage).
> This document describes verified code only. Roadmap/future ideas are not
> presented as current reality; see ROADMAP.md for the current strategic direction (A→C, P9 FINAL PASS). History at `24c72d0`/`71d2353`/`50429ad` preserved in docs/PROJECT_STATE.md.

---

# 1. High-Level Runtime

```text
User (CLI: agent_run.py)
      │  prompt
      ▼
Agent (simulation/agent/agent.py)
      │  loop.start(prompt)  ->  Kernel.dispatch(UserQuestionReceived)
      ▼
Planner (simulation/planner/planner.py)  ->  strategy name
      │
      ▼
StrategyDispatcher (simulation/agent/strategy_dispatcher.py)  ->  registry
      │  dispatch(strategy, agent, prompt)
      ├── calculator      -> CalculatorExecutor
      ├── memory_store    -> MemoryStoreExecutor
      ├── memory_recall   -> MemoryRecallExecutor
      ├── llm             -> LLMExecutor
      └── worker          -> WorkerExecutor -> WorkerAgent
             │
             ▼  (if worker) WorkerResult
      Agent.chat decides:
        - recovery_engine set?  -> BoundedRecoveryEngine.execute(...)
        - worker_pipeline set?  -> WorkerActionPipeline.execute(...)
        - else                    -> proposal-only, no mutation
      │
      ▼  (non-worker) Kernel.dispatch(AIResponseReceived)
```

---

# 2. Core Event Sourcing (simulation/core/)

| File | Responsibility |
|------|----------------|
| `event.py` | Immutable `Event` dataclass (event_type, payload, sequence, event_id) |
| `state.py` | Immutable `State` (tasks, workers, memory, conversation_history, worker_trace, event_counter) with `to_dict`/`from_dict` for snapshots |
| `reducer.py` | `Reducer.apply(state, event)`: TaskCreated / UserQuestionReceived / AIResponseReceived / MemoryStored / `Worker*` events -> worker_trace |
| `kernel.py` | `Kernel` dispatches events: assigns sequence, records DecisionTrace, applies reducer, appends to EventStore, triggers snapshot manager. Recovery runs on construction (`RecoveryEngine.recover()`). |

`Kernel.dispatch` is the single write path for all events, including worker
evidence events (simulation/core/kernel.py:40).

---

# 3. Persistence, Replay, Recovery (simulation/persistence|replay|recovery/)

- `EventStore` (`persistence/event_store.py`): append-only JSONL. Each
  record stores event_id, event_type, payload, sequence, previous_hash,
  current_hash (SHA-256 over the record, `HashChain.calculate`). Reads via
  `read_all` / `read_after`.
- `SnapshotStore` / `SnapshotManager` (`persistence/snapshot.py`,
  `persistence/snapshot_manager.py`): periodic snapshot every `interval`
  events (default 2).
- `RecoveryEngine` (`recovery/recovery_engine.py`): on Kernel start,
  verifies hash chain integrity, loads snapshot if present, replays only
  events after `last_sequence`. Raises RuntimeError on chain break.
- `ReplayEngine` (`replay/replay_engine.py`): deterministic replay with
  optional `initial_state`.
- The legacy `persistence/recovery.py` (`Recovery.rebuild`) was removed
  (commit `542c187`); the legacy unchained `persistence/event_store_backup.py`
  duplicate was removed in the P10.3-B hygiene cleanup (zero imports; not
  used by Kernel, which uses `simulation/recovery/recovery_engine.py`).

---

# 4. Runtime Orchestration

- `Planner` (`planner/planner.py`): keyword/prefix rules -> strategy:
  `worker:`, arithmetic, weather keywords, memory recall/store phrases,
  else `llm`. NOTE: `weather` strategy is produced but NOT registered in
  the dispatcher registry (dispatcher raises ValueError on unknown
  strategy) — a real gap (VERIFIED by code).
- `LoopEngine` (`loop/loop_engine.py`): start/next/verifying/complete/fail
  state machine; logs to stdout only.
- `DecisionTrace` (`decision/decision_trace.py`): in-memory step list with
  `record`/`clear`/`generate`; not persisted.
- `StrategyDispatcher` (`agent/strategy_dispatcher.py`): registers
  calculator, memory_store, memory_recall, llm, worker executors.
- Executors under `agent/executors/`: `BaseExecutor`, `CalculatorExecutor`,
  `MemoryStoreExecutor`, `MemoryRecallExecutor`, `LLMExecutor`,
  `WorkerExecutor`. `WorkerExecutor` builds a `WorkerTask` (task_id
  "worker-task", allowed_actions read/inspect/propose) and delegates to
  `WorkerAgent.run`.

---

# 5. Memory (simulation/memory/)

- `MemoryService`: pure functions over State (set/get/exists/delete/all).
- `MemoryEvents.stored/deleted`: build `MemoryStored`/`MemoryDeleted`
  events. `MemoryStored` is handled by the Reducer (memory dict).
- Executors: `memory_store_executor` (reads the prompt after "benim adım "
  and dispatches a MemoryStored event), `memory_recall_executor` (reads
  back from State and returns an AI response).

---

# 6. Tool Framework (simulation/tools/, simulation/services/)

- `BaseTool`, `Registry`, `Calculator` (arithmetic via safe exec).
- `services/tool_executor.py` remains (VERIFIED present);
  `services/runtime_service.py` (unused `Kernel` facade) was removed in
  the P10.3-B hygiene cleanup (zero imports). The executors path used by
  the dispatcher is `agent/executors/`, not `services/`.

---

# 7. Worker Action Pipeline (simulation/agent/pipeline/)

Proposal-to-apply chain. Active only when explicitly assembled
(`build_recovery_agent()` or `WorkerActionPipeline(...)` passed to Agent).

```text
WorkerResult (proposals)
   → [per patch] PatchValidator.validate  (scope/staleness/no-op)
   → [opt-in risk gate] RiskEngine.classify + RiskPolicy.decide
       → UNKNOWN/DENY stops here
       → HIGH/CRITICAL: ApprovalStore.find_valid(full context + patch
            object) consumes and binds the approval to the exact patch
            object + pipeline binding check
            (missing/malformed/expired/wrong/replayed ⇒ DENY)
   → Controller.approve(ValidationResult, approval?)  (typed, valid is True;
        binds the consumed approval_id into the decision)
   → ApplyVerifyPipeline.execute(patch, decision)
       → ApplyExecutor.apply
           → ApplyAuthorization.authorize  (typed ControllerDecision,
                approved is True, fingerprint match; when store-backed,
                HIGH/CRITICAL/UNKNOWN risk is recomputed at the boundary
                and the approval binding is re-verified via
                ApprovalStore.authorize_apply — single-use at apply,
                bound to the exact patch object)
           → FileApplier.apply (canonical path write + read-back + restore)
       → (if applied) VerificationExecutor.verify / verify_python_compile
   → PatchStageResult per patch; first failure stops the run
```

Pipeline failure stages: validation / controller / risk / approval /
apply_verify (worker_action_pipeline.py:46-60). Result contract
`WorkerPipelineResult` exposes apply_success, verification_passed,
evidence, stdout/stderr, exit_code, failure_stage.

Risk gate is OFF by default (`risk_gate_enabled` = both constructor args
provided; worker_action_pipeline.py:213). `build_recovery_agent` enables
it only when the caller explicitly passes `risk_engine` and `risk_policy`
(MISSION-011 opt-in; default stays off by design, D-021/D-022). When
active the flow is: RiskEngine.classify -> RiskPolicy.decide ->
(UNKNOWN/DENY stops, HIGH/CRITICAL requires approval) -> Controller ->
ApplyVerifyPipeline with the policy-chosen verification depth. VERIFIED —
`tests/risk_pipeline_test.py`, `tests/approval_boundary_test.py`.

RiskEngine (MISSION-018A) classifies content into SAFE / SUSPICIOUS /
OPAQUE before producing a level: SAFE content may keep the LOW/MEDIUM
baseline; SUSPICIOUS credential-like material (JSON/YAML/TOML credential
keys, bare token prefixes, base64/encoded material, URL userinfo, shell
credential flags, env secret references, authorization headers/Bearer) is
elevated to HIGH (approval); OPAQUE content (control characters) yields
UNKNOWN -> DENY. `not detected` is never treated as `safe`. Path signals
additionally cover backup/temp suffixes, hidden credential files,
credential directories and production-env naming. Trivial assignments
(`self.token = None`) stay benign. VERIFIED — `tests/risk_regression_test.py`,
`tests/risk_pipeline_test.py`, adversarial corpus A37-A50.

Human approval (MISSION-012/014): `Approval` is a frozen, fingerprint/path/
action/risk/attempt/expiry-bound single-use contract; `ApprovalStore` is
fingerprint-keyed and consumes approvals on `find_valid` (which requires
the full authorization context and binds the exact patch object). The
pipeline validates the returned object itself (`_approval_is_valid`), and
the store-backed apply boundary re-verifies the consumed approval binding
(`ApprovalStore.authorize_apply`) at the narrowest point — so a missing,
malformed, expired, wrong, replayed, forged or differently-object-bound
approval always fails closed, and proposal-contained/agent-fabricated
approval metadata is never authority. Grants are recorded as
`WorkerHumanApprovalGranted` evidence events.

---

# 8. Worker (simulation/agent/worker/)

- `WorkerAgent`: enforces `WorkerPolicy` + task `allowed_actions`
  (empty = unconstrained, non-empty = fail-closed), checks read path scope
  via `PathPolicy`, reads files, calls the analyzer, verifies
  `old_text` occurs exactly once, builds `PatchProposal` (full-file
  old/new content).
- `LLMCodeAnalyzer`: prompts an LLM provider, parses JSON into
  `AnalysisResult` with fail-closed validation (MISSION-010); strips code
  fences; rejects malformed/missing fields.
- `AnalysisResult`: frozen contract; `confidence`/`risk` are advisory
  only (risk authority is the RiskEngine).
- `PatchProposal`: frozen; deterministic SHA-256 `fingerprint()` over all
  fields.
- `PatchValidator`: action=="modify", scope check, existence/is_file,
  exact current-content==old_content, non-empty change.
- `WorkerExecutor`: builds WorkerTask and runs WorkerAgent.

---

# 9. Apply & Verification

- `Controller` (`agent/controller/controller.py`): approves only when
  `validation.valid is True` (strict identity) and action=="modify";
  malformed/missing validation fails closed. Message text is never the
  signal (MISSION-007). When a consumed `Approval` is supplied it is bound
  into the decision (`approval_id`); a malformed or wrong-fingerprint
  approval is rejected (MISSION-014).
- `ApplyAuthorization`: requires a real `ControllerDecision` with
  `approved is True` and `decision.patch_fingerprint == patch.fingerprint()`.
  When store-backed (risk gate enabled), it recomputes the patch risk
  deterministically at the boundary and, for HIGH/CRITICAL/UNKNOWN,
  requires a store-verified approval binding consumed exactly once at the
  apply boundary (`ApprovalStore.authorize_apply`). Fake objects, forged
  decisions, agent-claimed approval ids, replayed/expired approvals,
  evidence-only metadata and object-substituted approvals fail closed
  (MISSION-014).
- `FileApplier`: re-checks scope via `PathPolicy.resolve_target`
  (canonical path), reads current content, requires exact
  `old_content` match at write time, writes, reads back, and restores on
  mismatch (MISSION-006).
- `VerificationExecutor` (`agent/verify/verification_executor.py`):
  `verify` = compileall + pytest; `verify_python_compile` = compile only.
  Commands run as arg lists (no shell). PASS/FAIL with evidence. Both
  depths are tested (MISSION-011); the risk policy currently selects
  `compile+tests` for every non-deny level.
- `CommandRunner`: subprocess.run with timeout; captures stdout/stderr.

---

# 10. Bounded Recovery (simulation/agent/recovery/)

- `BoundedRecoveryEngine`: iterative loop over a single attempt counter,
  hard cap `MAX_ATTEMPTS_CAP = 3`; verification FAIL retries if budget
  remains; validator/controller/apply failures are terminal; duplicate
  fingerprint suppression; exceptions terminal. Never recurses.
- `RecoveryAttempt` / `RecoveryResult`: append-only evidence contracts
  with final_apply/verification accessors.
- `recovery_assembly.build_recovery_agent()`: the ONLY production wiring
  that enables apply+verify+recovery; binds a `WorkerEvidenceRecorder`
  backed by the Kernel. Optional `risk_engine`/`risk_policy` parameters
  expose the pipeline risk gate as an explicit opt-in (off by default,
  D-021). **RECOVERY authorization (MISSION-018B):** the apply boundary
  recomputes risk and DENIES every HIGH/CRITICAL/UNKNOWN apply without a
  store-verified approval, so even a gate-off assembly can never mutate
  such a patch. Every retry is an independent PatchProposal through
  validation -> risk -> approval -> controller -> store-backed apply ->
  verification; attempt binding prevents an older approval from
  authorizing a newer patch. `agent_run.py --recovery` wires the risk gate
  + approval store + ledger (pre-authorized autonomous retry); GOVERNED
  additionally wires the interactive `ConsoleApprovalGateway`. The retry
  budget never substitutes for human authorization.

---

# 11. Evidence Recording (simulation/agent/evidence/)

- `WorkerEventType`: 13 worker lifecycle event types
  (WorkerTaskCreated ... WorkerRecoveryFailed).
- `build_worker_event`: factory with allow-list.
- `WorkerEvidenceRecorder`: dispatches events via `kernel.dispatch`
  (so sequence/hash-chain/snapshot/replay all apply) and mirrors steps
  into DecisionTrace. Payload contract: fingerprints and status only,
  never patch content / stdout / stderr / secrets.

---

# 12. Security (simulation/security/)

- `PathPolicy`: fail-closed path scope. Canonicalization via
  `Path.resolve(strict=False)` + `os.path.normcase`; `..` components
  rejected; containment via `_within`; symlink/junction escape detected;
  empty/None scope fails closed.
- `HashChain` / `HashVerifier`: SHA-256 chaining; `verify` recomputes
  from GENESIS and returns False on break (prints "Hash bozuk:" —
  informational, no secrets).
- `RiskEngine` / `RiskPolicy` / `RiskLevel` (MISSION-011, hardened
  MISSION-018A): deterministic system-derived risk from path/action/
  change-size/content signals; advisory LLM risk can only raise the level;
  policy maps UNKNOWN->DENY, HIGH/CRITICAL->human approval, LOW/MEDIUM->
  auto (max_attempts bounded). MISSION-018A adds fail-closed content
  classification (SAFE / SUSPICIOUS / OPAQUE; `not detected` is never
  `safe`), path hardening (backup/temp, hidden credential files,
  credential dirs, production-env naming) and a MISSION-018A regression
  corpus. Tested (tests/risk_*.py, MISSION-011/018A). The gate is opt-in:
  active only when both `risk_engine` and `risk_policy` are passed to
  `WorkerActionPipeline` / `build_recovery_agent`.

# 12a. Human Approval Boundary (simulation/agent/approval/, MISSION-012/014)

- `Approval` (frozen): single-use authorization bound to patch
  fingerprint, path, action, risk level, attempt, authorizer, created_at
  and expires_at. Fail-closed construction (malformed/missing fields
  raise; only HIGH/CRITICAL risk labels are valid approval targets).
- `ApprovalStore`: fingerprint-keyed; `grant(...)` persists and records a
  `WorkerHumanApprovalGranted` evidence event; `find_valid(fingerprint,
  path, action, risk_level, attempt, patch=None)` requires the complete
  authorization context (missing path/action/risk/attempt fails closed),
  returns the first unexpired, unconsumed approval matching the full
  context, consumes it and binds it to the exact patch object.
  `authorize_apply(approval_id, patch)` is the single-use apply-boundary
  consumption: it verifies the approval was granted by this store, was
  released by `find_valid`, is bound to this exact patch object, is not
  expired, and matches fingerprint/path/action.
- Pipeline enforcement (`_approval_is_valid`): the pipeline independently
  re-validates the returned object's type and every binding field, and the
  store-backed apply authorization re-verifies the consumed approval
  binding at apply time, so substitution/replay/forgery/
  metadata-injection all fail closed.
- Tested (tests/approval_boundary_test.py, 48 tests incl. MISSION-014
  A–O; corpus A13-A20, MISSION-013).

# 12b. Interactive CLI Human-Approval Interface (simulation/agent/approval/approval_console.py, MISSION-017)

- `PendingApprovalRequest`: immutable human-readable snapshot built from
  the real `PatchProposal` + `RiskAssessment`; renders fingerprint, path,
  action, risk level + context, attempt, expiry, authorizer and evidence
  reference (never patch content).
- `prompt_approval_decision(request, store, input_fn, print_fn)`: renders
  the request and routes an explicit human approve into
  `ApprovalStore.grant(...)` with the request-derived context; deny / EOF /
  unrecognized input return `None` (fail-closed). `input_fn`/`print_fn`
  are injectable for deterministic tests.
- `ConsoleApprovalGateway.request_approval(patch, risk_level, attempt,
  evidence_reference)`: recomputes the risk with the system `RiskEngine`;
  refuses when the pipeline-provided risk differs (no downgraded display),
  then prompts the human. Wired into `WorkerActionPipeline` as
  `approval_gateway` (consulted only when no valid stored approval exists)
  and into `agent_run.py --governed`.
- Flow: pipeline STAGE_APPROVAL → `find_valid` returns None →
  `approval_gateway.request_approval(...)` → human approves →
  `store.grant(...)` → pipeline re-consumes via `find_valid(patch=patch)`
  (object-identity binding + single-use preserved) → controller → apply →
  verify → evidence. The gateway is never an authority; the store/apply
  boundary remain the authority.

---

# 13. LLM Providers (simulation/llm/)

- `BaseProvider` ABC + `ProviderError`.
- `OpenRouterProvider`: requests.post with `timeout=(10,120)`, fail-closed
  ProviderError on HTTP>=400 / network / JSON errors, secret-safe logging
  (only status code + model at DEBUG), no response-body prints
  (MISSION-003).
- `ProviderFactory.create()` -> OpenRouterProvider (only provider).
- Default model: `deepseek/deepseek-chat`.

---

# 14. Shipped Entry Point (agent_run.py)

- `--governed` flag: uses `build_recovery_agent` with
  `RiskEngine`/`RiskPolicy` + a durable ledger-backed `ApprovalStore`.
  Requires `--allowed-path`. LOW/MEDIUM auto-apply (with rollback on
  verification failure); HIGH/CRITICAL fail closed without a valid approval
  (MISSION-016).
- `--recovery` flag: uses `build_recovery_agent` (no risk gate).
- `--allowed-path` (repeatable): worker read/propose/apply scope;
  empty by default (fail-closed, no mutations).
- `--approval-ledger <path>`: durable approval ledger for `--governed`.
- Default: `Agent(kernel)` proposal-only chat loop.
- REPL prompts in Turkish; on "exit"/"quit" exits.

# 14b. Governed CLI (P2.1/P2.2/P2.2-FP, `agent_run.py:154`)

Thin wrappers over the same `WorkerActionPipeline`+`GovernanceEvaluator`+`ApprovalStore`+`ApplyOutcomeJournal` (isolated per-workspace `.cli_platform`, no global `data/` pollution):

- `python agent_run.py apply --file <f> --old-content <o> --new-content <n> --workspace <ws>` — single patch through governed pipeline (P2.1).
- `python agent_run.py approve --file ... --workspace <ws>` — manual grant (P2.1); `approve --pending --workspace <ws>` — mechanical grant from `pending_proposals.json` exact proposal (P2.2-FP fingerprint parity, includes `allowed_paths`+reason+old/new).
- `python agent_run.py task --goal "..." --workspace <ws> [--file <f>] --fake-analyzer [--dry-run]` — natural-language `WorkerAgent` -> `PatchProposal` -> governed pipeline (P2.2). Persists `pending_proposals.json` for `--pending`.
- `python agent_run.py history|status --workspace <ws>` — read-only `ApplyOutcomeJournal` inspection (no mutation).
- Demo: `powershell -ExecutionPolicy Bypass -File demo_cli.ps1` — HIGH DENY -> `approve --pending` -> VERIFIED -> replay DENY -> `history` (P2.3-A).

# 14a. MISSION-016 Hardening (verified code)

- **Rollback:** `ApplyExecutor.rollback` -> `FileApplier.restore` (atomic
  tempfile+replace + read-back). `ApplyVerifyPipeline` rolls a
  failed-verification patch back to its exact pre-apply content and (when
  the verification executor supports it) re-verifies the clean state with a
  compile-only check. Rollback failure is classified `FAILURE_ROLLBACK`
  (terminal; recovery never retries on an unknown state). Events:
  `WorkerRollbackSucceeded` / `WorkerRollbackFailed`.
- **Approval ledger:** `ApprovalLedger` is an append-only, hash-chained
  file (grant/consumed/applied). `ApprovalStore` reloads authorization state
  from it; consumed/applied approvals stay so after restart; corrupt or
  hash-broken ledger state raises `RuntimeError` (fail-closed). Evidence
  events remain evidence-only (D-012).
- **Event store:** cached chain head (O(1) append), per-instance lock,
  per-append fsync, store-authoritative `next_sequence()`. Snapshot carries
  a `content_hash` and a `last_sequence`; unverifiable/inconsistent
  snapshots fall back to a full replay from the chain-verified event log;
  event-chain corruption still raises.
- **Verification:** default 120s timeout; pytest exit code 5 ("no tests
  collected") is FAIL; `PYTHONPYCACHEPREFIX` redirects bytecode cache out of
  the tree.
- **Secret boundary:** `secret_policy.py` classifies secret files
  (`.env`, PEM keys, credential files) and redacts obvious inline secret
  values; the worker skips secret files and sends only redacted content to
  the analyzer; the analyzer prompt marks content as UNTRUSTED DATA;
  proposals referencing `[REDACTED]` are rejected.
- **Lazy provider:** `Agent`/`LLMExecutor`/`LLMCodeAnalyzer` resolve the
  provider only on a real LLM call.

---

# 14c. Governed External-Action Pipeline (post-P9, `b2d6da7..d42736d`)

Implemented and tested surface for governed external (non-file) provider
calls, reusing the existing file-governance authority without a second
execution path. Described strictly from current source and tests; no
universal correctness or complete crash/interleaving coverage is claimed.

- `ExternalAction` (`simulation/agent/apply/external_action.py`): frozen
  contract; deterministic SHA-256 fingerprint over
  provider/operation/payload/idempotency_key/reason; projects onto the
  existing governance chain as a synthetic `PatchProposal` with path
  `external://{provider}/{operation}` and action `modify`, so
  `PathPolicy` scope checks remain meaningful (`allowed_paths` must
  contain the external scope, e.g. `external://`). The `idempotency_key`
  is deterministically encoded into the synthetic fingerprint, so
  different keys produce different approval-binding identities.
- `ExternalActionPipeline` (`simulation/agent/pipeline/external_action_pipeline.py`):
  full governance chain (scope → governance/risk via the synthetic patch →
  approval → controller → executor). Attempt authority comes ONLY from
  `intent_id` (initial execution → attempt 1) or a journal-issued
  `AttemptContext` (retry); a raw integer attempt is rejected fail-closed.
  Retry additionally requires exact approval_id + attempt correlation
  between the context, the store approval and the controller decision.
- `ExternalActionExecutor` (`simulation/agent/apply/external_executor.py`):
  fail-closed executor; requires an `ExternalOutcomeJournal` (no
  in-memory fallback — a missing journal is a configuration failure);
  records intent/started before the provider call and all four outcomes
  (KNOWN_SUCCESS / KNOWN_FAILURE / TIMEOUT_UNKNOWN / AMBIGUOUS_UNKNOWN)
  after it; ambiguous outcomes are never promoted to success; no
  auto-retry, no compensation, no provider call on any authorization or
  journal-validation failure.
- `ExternalOutcomeJournal` (`simulation/agent/apply/external_outcome_journal.py`):
  append-only, hash-chained, secret-safe JSONL (payload/idempotency stored
  as SHA-256 hashes only), process-locked, fail-closed load (hash
  mismatch / chain break / invalid transition raises). `open_attempt`
  issues a hash-bound `AttemptContext` (intent_id, approval_id,
  previous_hash, expected_previous_attempt); `start_opened_attempt`
  validates the durable attempt, approval_id correlation, previous-hash
  lineage and fingerprint before any provider call — the durable journal
  lineage, not any in-memory session state, is the attempt authority.
- `SessionGovernedBridge.execute_external`
  (`simulation/agent/session/session_governed_bridge.py`): the only place
  an `AgentSession` submits an external action; passes only
  `intent_id`/`attempt_context` to the pipeline and never
  `session.attempt`. Production code contains no
  `AgentSession.next_attempt()` call — AgentSession is NOT the external
  attempt authority (VERIFIED by `tests/test_external_t_b10_a.py`).
- `external_reconciliation.py`: durable-lineage reconciliation for
  external intents (detection over the journal).
- Runtime wiring: `agent_run.py external` CLI subcommand (isolated
  per-workspace `.cli_platform/external_journal.jsonl`); session wiring
  via `session_governed_bridge.py` (commit `455090f`).
- Test evidence: `tests/test_external_t_b1..b10*`,
  `tests/test_external_model_b_production.py`,
  `tests/test_external_idempotency_binding.py`,
  `tests/test_external_f4_no_journal_bypass.py`,
  `tests/test_external_runtime_wiring_m12.py`,
  `tests/test_external_cli_t11a.py`,
  `tests/test_pipeline_integration_p11.py` — included in the local
  full-suite PASS at `d42736d` (1272/1259/13/0, local Windows run;
  local evidence only, NOT hosted CI).

---

# 15. MISSION-019: Governance Consolidation & Crash Consistency

- **Single governance authority (`simulation/security/governance_evaluator.py`, D-031):** one `GovernanceEvaluator` wraps one `RiskEngine` + one `RiskPolicy`. `WorkerActionPipeline` builds it, `ConsoleApprovalGateway` consumes it, and `WorkerActionPipeline._bind_approval_authority` rebinds the apply executor's `ApplyAuthorization` to the *same* evaluator (engine identity), so the pipeline / console / apply boundary can never diverge on risk classification. The apply boundary keeps its independent fail-closed checks (typed decision, `approved is True`, fingerprint, store-backed approval). MISSION-018A/018B semantics unchanged.
- **Apply-outcome journal (`simulation/agent/apply/apply_outcome_journal.py`, D-032):** append-only, hash-chained, secret-safe lifecycle record (INTENT -> APPLY_STARTED -> APPLIED/APPLY_FAILED -> VERIFIED/ROLLBACK_STARTED -> ROLLED_BACK/ROLLBACK_FAILED) written around the real file write by `ApplyExecutor` + `ApplyVerifyPipeline`. `load()` fails closed on corruption / out-of-order / duplicate transitions. Wired via `WorkerActionPipeline(apply_journal=...)`, `build_recovery_agent(apply_journal=...)` and `agent_run.py --apply-journal`.
- **Detect-only reconciliation (`simulation/agent/recovery/startup_reconciliation.py`, D-032):** `ReconciliationEngine.detect()` classifies journaled intents, inspects in-scope files against journaled content hashes, and flags orphaned mutations / consumed approvals without a terminal outcome. Never writes a file; repair is deliberately out of scope (a mutation needing explicit authorization).
- **Atomic snapshots (D-033):** `SnapshotStore.save` uses temp + fsync + `os.replace`; recovery's unverifiable-snapshot fallback is unchanged.
- **Kernel semantics (documented):** append -> trace -> reducer; a reducer failure persists the event, diverges live state, and replay reproduces the failure (fail-closed).
- **Retry-evidence redaction (D-034):** verification stdout/stderr is redacted + length-bounded before the next LLM retry prompt.
- New `--apply-journal` CLI flag; `--recovery`/`--governed` run startup reconciliation on boot.

---

# 16. Known Architectural Gaps (code-verified)

- Human approval boundary implemented, hardened and given a CLI UX
  (MISSION-012/014/016/017): `ConsoleApprovalGateway` +
  `approval_console.py` route explicit human decisions into
  `ApprovalStore.grant` and are wired into `agent_run.py --governed`.
  The interface is synchronous (blocks the governed run until the operator
  decides; EOF fails closed).
- Risk gate / governed apply DEFAULT OFF: `--governed`/`--recovery` are the
  explicit opt-ins; the shipped default runtime stays proposal-only
  (D-021/D-022/D-015). Default-on remains an open productization decision
  now that a human-approval UX exists.
- Rollback on verification failure is provided by the real `ApplyExecutor`;
  a custom executor without `rollback` leaves the failed state (documented).
- `DecisionTrace` in-memory only.
- `simulation/domain/` and the remaining `services/tool_executor.py`
  overlap with active modules (historical overlaps `persistence/recovery.py`,
  the `snapshot/snapshot_manager.py` duplicate, the empty
  `simulation/snapshot/` package and `persistence/event_store_backup.py`
  were removed in commits `542c187`, `07dbd34` and the P10.3-B hygiene
  cleanup).
- Empty test subpackages `tests/chaos|integration|property|unit/`.
- Multi-process writers on one `EventStore` file are unsupported (same-store
  threads are safe via the internal lock).
- The `weather` planner branch was removed (was unroutable); the
  planner/dispatcher contract test now locks the invariant that every
  emitted strategy is registered.
- Secret redaction and prompt-injection resistance are mitigations, not
  guarantees (see SECURITY_MODEL.md).
