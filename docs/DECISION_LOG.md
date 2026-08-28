# DECISION_LOG.md

Record of significant design decisions and their evidence. Each decision is
classified VERIFIED (documented + code/test evidence), INFERRED (reasoned
from behavior, not explicitly recorded), or UNKNOWN.

---

## D-001 — RecoveryEngine orchestrates replay; ReplayEngine stays deterministic
- **Date:** 2026-08-06 (RFC-001)
- **Status:** ACCEPTED, **VERIFIED** — ADR-001, docs/rfc/RFC-001-Recovery-Engine.md,
  `simulation/recovery/recovery_engine.py` + `simulation/replay/replay_engine.py`
- **Decision:** Recovery is a separate orchestration concern (snapshot +
  hash-integrity + replay); ReplayEngine remains a pure deterministic
  replay primitive.
- **Consequences:** Kernel constructs a RecoveryEngine at startup
  (simulation/core/kernel.py:26); replay stays stateless.

## D-002 — Events are the source of truth; state is a projection
- **Status:** ACCEPTED, **VERIFIED** — docs/FOUNDING_PRINCIPLES.md (#4),
  docs/PHILOSOPHY.md; `Reducer.apply` rebuilds State from events;
  snapshots are serialized State projections
  (`simulation/persistence/snapshot.py`).

## D-003 — The runtime is provider-agnostic; LLM providers are replaceable
- **Status:** ACCEPTED, **VERIFIED (single provider)** — docs/FOUNDING_PRINCIPLES.md
  (#2/#3); `BaseProvider` ABC + `ProviderFactory`
  (simulation/llm/base_provider.py, provider_factory.py).
- **Note:** Only one provider (OpenRouter) is implemented. Multi-provider
  interchange is **VERIFIED** by abstraction but **UNVERIFIED** by tests
  beyond OpenRouter.

## D-004 — AI proposes; deterministic layers decide
- **Status:** ACCEPTED, **VERIFIED** — VISION.md, ROADMAP.md Rule 2
  ("AI Is Not Authority"); WorkerAgent only proposes; Controller/Apply/
  Verification decide; `confidence`/`risk` are advisory
  (analysis_result.py:27-38, MISSION-010).

## D-005 — Apply success is never verification success
- **Status:** ACCEPTED, **VERIFIED** — ROADMAP.md Rule 3;
  `ApplyVerifyPipeline` returns success only when apply AND verification
  passed (apply_verify_pipeline.py:67); tests
  `test_apply_success_verification_failure_is_pipeline_failure`,
  adversarial A08/A09.

## D-006 — No unlimited self-modification; retry is bounded
- **Status:** ACCEPTED, **VERIFIED** — ROADMAP.md Rule 4;
  `BoundedRecoveryEngine.MAX_ATTEMPTS_CAP = 3`
  (bounded_recovery_engine.py:60); no recursion; duplicate fingerprints
  stop retries.

## D-007 — Apply is NOT active by default (fail-closed default runtime)
- **Status:** ACCEPTED, **VERIFIED** — MISSION-004 design decision; default
  `Agent(kernel)` is proposal-only; apply+verify+recovery only via
  `build_recovery_agent()` or `agent_run.py --recovery`; tests
  `test_default_agent_runtime_is_proposal_only_no_apply_no_verify`.

## D-008 — Path scope enforced by canonical containment, not string equality
- **Status:** ACCEPTED, **VERIFIED** — docs/SECURITY_BASELINE.md finding B;
  `PathPolicy.check_scope` (resolve + normcase + `_within`);
  path_security_test.py.

## D-009 — Approval bound to a typed contract, not a message string
- **Status:** ACCEPTED, **VERIFIED** — MISSION-007; `ValidationResult`;
  Controller decides on `valid is True` only
  (controller.py:39); message text never the signal;
  controller_decision_test.py.

## D-010 — Approved patch == applied patch (fingerprint + read-back)
- **Status:** ACCEPTED, **VERIFIED** — MISSION-006; `ApplyAuthorization`
  fingerprint match; `FileApplier` canonical-path write + read-back +
  bounded restore; patch_integrity_test.py.

## D-011 — LLM analysis must be a structured, fail-closed contract
- **Status:** ACCEPTED, **VERIFIED** — MISSION-010; `AnalysisResult` frozen
  dataclass with strict construction rules; non-ActionResult analyzer
  returns rejected; structured_analysis_test.py.
- **Note:** backward compatibility with the old `(diagnosis, old_text,
  new_text)` tuple deliberately NOT preserved (weaker contract).

## D-012 — Evidence recorded through the existing event-sourcing path only
- **Status:** ACCEPTED, **VERIFIED** — MISSION-004; no parallel evidence
  store; `WorkerEvidenceRecorder` dispatches normal Events via
  `kernel.dispatch` (hash-chain preserved); worker_evidence_test.py.

## D-013 — Event payloads are secret-safe (fingerprints, not content)
- **Status:** ACCEPTED, **VERIFIED** — MISSION-004; patch content and
  verification stdout/stderr never in payloads
  (worker_events.py:7, worker_evidence_recorder.py:22);
  `test_payloads_never_contain_patch_content_or_command_output`.

## D-014 — DecisionTrace is in-memory; event log is the durable evidence
- **Status:** ACCEPTED, **VERIFIED** — SECURITY_BASELINE.md finding F;
  `DecisionTrace` steps list (decision_trace.py:5); recorded on every
  dispatch and worker event; not persisted.

## D-015 — Recovery in the shipped entry point is opt-in (`--recovery`)
- **Status:** ACCEPTED, **VERIFIED** — agent_run.py:20-28; default stays
  proposal-only. Making it default is an open product decision.

## D-016 — Risk classification is system-derived; LLM risk is advisory-only
- **Status:** ACCEPTED, **VERIFIED (tests)** — MISSION-011;
  `RiskEngine` derives level from signals; advisory risk only raises;
  UNKNOWN => DENY (risk_engine.py:123, risk_policy.py:84). Covered by
  `tests/risk_engine_test.py` / `tests/risk_policy_test.py` (83 risk tests).

## D-017 — Empty task.allowed_actions = unconstrained (backward compatible)
- **Status:** ACCEPTED, **VERIFIED** — MISSION-005; non-empty = fail-closed
  (worker_agent.py:262); worker_read_scope_test.py.

## D-018 — Provider errors are fail-closed single type `ProviderError`
- **Status:** ACCEPTED, **VERIFIED** — MISSION-003; HTTP>=400 / network /
  JSON errors wrapped; secret-safe logging; llm_provider_test.py.

## D-019 — Verification commands run as arg lists, never via a shell
- **Status:** ACCEPTED, **VERIFIED** — CommandRunner `shell=False`
  (command_runner.py:38); verification_executor_test.py.

## D-020 — Empty task.allowed_actions and empty allowed_paths fail closed
- **Status:** ACCEPTED, **VERIFIED** — WorkerAgent rejects empty
  `allowed_paths` ("No allowed paths were provided.",
  worker_agent.py:83); PathPolicy fails closed on empty/None scope.

## D-021 — Risk gate is an explicit opt-in, not default-on in the assembly
- **Status:** ACCEPTED, **VERIFIED** — MISSION-011 close-out (2026-08-12).
- **Decision:** `build_recovery_agent` accepts optional `risk_engine` /
  `risk_policy`; the gate activates only when BOTH are passed. Default
  behavior (gate off) is unchanged. The pipeline-level gate
  (`WorkerActionPipeline(risk_engine=..., risk_policy=...)`) was already
  opt-in by construction (`risk_gate_enabled` requires both args).
- **Evidence:** `tests/risk_pipeline_test.py` (gate on/off, risk denial,
  HIGH/CRITICAL approval boundary, depth propagation);
  `recovery_assembly.py` signature + defaults.
- **Rationale (why not default-on):** HIGH/CRITICAL require human approval,
  which depended on the `approval_store` contract that had no
  implementation (MISSION-012). Wiring the gate into the shipped assembly
  would silently hard-block every HIGH/CRITICAL patch with no resolution
  path. Keeping it opt-in preserves backward compatibility, does not weaken
  any security boundary, and lets MISSION-012 re-evaluate default-on when
  an approval store exists.
- **Re-evaluated by MISSION-012 (D-022):** the approval store now exists,
  but the gate still stays explicit opt-in. See D-022.

## D-022 — Approval model is single-use, fully bound and evidence-recorded
- **Status:** ACCEPTED, **VERIFIED** — MISSION-012 (2026-08-12).
- **Decision:** Human approval is a frozen `Approval` bound to patch
  fingerprint, path, action, risk level, attempt, authorizer and expiry.
  `ApprovalStore.find_valid` returns the first unexpired, unconsumed
  approval matching the full context and consumes it (single-use; replay
  impossible). The pipeline independently re-validates the returned
  object's type and every binding field (`_approval_is_valid`), so
  agent-fabricated or proposal-contained approval metadata is never
  authority. Every grant is recorded as a `WorkerHumanApprovalGranted`
  event through the existing Kernel/event store (no parallel evidence
  architecture). Malformed/missing/expired/wrong/replayed approvals all
  DENY at the approval stage.
- **Evidence:** `simulation/agent/approval/` +
  `tests/approval_boundary_test.py` (31 tests) + corpus A13-A20 +
  `tests/risk_pipeline_test.py` (updated stubs to real `Approval` objects).
- **Default-gate consequence:** the risk gate remains DEFAULT OFF /
  explicit opt-in. The approval store removes the hard-block, but turning
  the gate on in the shipped assembly is now a productization decision the
  repository's current evidence base does not require; it stays off by
  default (backward compatible, no security boundary loosened).

## D-023 — The apply authorization boundary is store-backed and fail-closed
- **Status:** ACCEPTED, **VERIFIED** — MISSION-014 (2026-08-12).
- **Decision:** `ApplyAuthorization` never trusts duck-typed metadata. It
  requires a real `ControllerDecision` with `approved is True` and an
  exact fingerprint match. When bound to the approval authority (risk gate
  enabled) it recomputes the patch risk deterministically at the boundary
  and, for HIGH/CRITICAL/UNKNOWN applies, requires a store-verified,
  single-use approval binding: `ControllerDecision.approval_id` +
  `ApprovalStore.authorize_apply(approval_id, patch)` which verifies the
  approval was granted by that store, released by `find_valid`, bound to
  the exact patch object, not expired, and not already applied. The
  approval-to-apply binding is explicit (approval identity + patch object
  identity), not merely transitive through a shared `PatchProposal`.
- **Rationale:** MISSION-012's pipeline-level approval gate was necessary
  but not sufficient: a forged/agent-controlled decision object carrying
  `approved=True` + the matching fingerprint could still reach the apply
  authorization, and the boundary did not itself verify the human-approval
  authority. Enforcing at the narrowest trusted boundary (the store-backed
  apply authorization) makes the failure mode structural, not a
  well-behaved-caller assumption.
- **Consequence:** the gate stays DEFAULT OFF (D-021/D-022): a default
  `ApplyExecutor()`/`WorkerActionPipeline()` keeps the historical
  typed-decision + fingerprint contract. No security boundary was loosened;
  the default runtime remains proposal-only.
- **Evidence:** `simulation/agent/apply/apply_authorization.py`,
  `simulation/agent/approval/approval_store.py`,
  `simulation/agent/controller/controller.py`,
  `simulation/agent/controller/controller_decision.py`,
  `tests/approval_boundary_test.py` (48 tests, MISSION-014 A–O).

---

## D-024 — Verification FAIL rolls the patch back to the pre-apply state
- **Status:** ACCEPTED, **VERIFIED** — MISSION-016 (2026-08-12).
- **Decision:** `ApplyVerifyPipeline` restores the exact pre-apply content
  via `ApplyExecutor.rollback` -> `FileApplier.restore` when verification
  fails after a successful apply, and (when supported) re-verifies the clean
  state with a compile-only check. A rollback failure is a terminal
  `FAILURE_ROLLBACK`; the bounded recovery loop never retries on an unknown
  or corrupted state, so recovery works from clean state with no cumulative
  modifications.
- **Evidence:** `tests/rollback_test.py`, `tests/apply_verify_pipeline_test.py`,
  corpus A21/A22, updated recovery/evidence tests.

## D-025 — Approval single-use state is durable via a dedicated ledger
- **Status:** ACCEPTED, **VERIFIED** — MISSION-016 (2026-08-12).
- **Decision:** `ApprovalLedger` (append-only, hash-chained) records
  grant/consumed/applied transitions; `ApprovalStore` reloads authorization
  state from it so a consumed/applied approval stays so after a restart.
  Corrupt state raises `RuntimeError` (fail-closed). The ledger is separate
  from the evidence event stream so D-012 / test_m ("evidence is never an
  authorization input") is preserved.
- **Evidence:** `tests/approval_durability_test.py`, corpus A23/A24,
  `tests/approval_boundary_test.py::test_m_*`.

## D-026 — Event store: O(1) append, sequence authority, atomic snapshots
- **Status:** ACCEPTED, **VERIFIED** — MISSION-016 (2026-08-12).
- **Decision:** `EventStore` caches the chain head (O(1) append), serializes
  appends with a per-instance lock, fsyncs, and is the sequence authority
  (`next_sequence`). Snapshots carry a `content_hash` and are only trusted
  when it verifies and `last_sequence` is consistent with the store;
  otherwise recovery falls back to a full replay from the chain-verified
  event log. Event-chain corruption still raises.
- **Evidence:** `tests/event_store_concurrency_test.py`,
  `tests/snapshot_integrity_test.py`, corpus A28/A29, benchmark
  `benchmarks/event_store_benchmark.py` (linear append rate).

## D-027 — Secret files are skipped and inline secrets redacted pre-analyzer
- **Status:** ACCEPTED, **VERIFIED** — MISSION-016 (2026-08-12).
- **Decision:** The worker never sends whole secret files
  (`.env`, PEM keys, credential files) to the LLM analyzer and redacts
  obvious inline secret values; proposals referencing `[REDACTED]` are
  rejected; the analyzer prompt marks content as UNTRUSTED DATA. This is a
  heuristic mitigation, not a guarantee.
- **Evidence:** `tests/secret_boundary_test.py`, corpus A25/A26.

## D-028 — Human approval UX is a minimal, safe CLI interface (MISSION-017)
- **Status:** ACCEPTED, **VERIFIED** — MISSION-017 (2026-08-13).
- **Decision:** The human-approval flow is an interactive CLI
  (`simulation/agent/approval/approval_console.py`: `PendingApprovalRequest`,
  `prompt_approval_decision`, `ConsoleApprovalGateway`) rather than a web
  UI or API. The interface renders the full authorization context
  (fingerprint, path, action, risk level + context, attempt, expiry,
  authorizer, evidence reference) and routes an explicit human approve/deny
  into `ApprovalStore.grant`. It is wired into `WorkerActionPipeline`
  (`approval_gateway`, consulted only when no valid stored approval exists)
  and `agent_run.py --governed`. The gateway is never an authority:
  displayed == granted == applied by construction (all derived from the real
  patch + system risk), a risk downgrade is refused, deny/EOF fail closed,
  and the grant still flows through `find_valid`/`authorize_apply`.
- **Evidence:** `tests/approval_console_test.py` (23 tests), corpus
  A31-A36, `tests/runtime_mode_test.py`.
- **Default-gate consequence:** the risk gate stays DEFAULT OFF. A
  human-approval UX now exists, so the default-on decision (D-021/D-022)
  becomes a pure productization choice with no missing implementation
  dependency — still **UNKNOWN** until a product decision is made.

## D-029 — Risk content classification is fail-closed: "not detected" is not "safe" (MISSION-018A)
- **Status:** ACCEPTED, **VERIFIED** — MISSION-018A (2026-08-13).
- **Decision:** `RiskEngine` no longer treats the absence of a known HIGH
  pattern as proof of low risk. Content is classified into three states
  before a level is produced: SAFE (plain content) may keep the LOW/MEDIUM
  baseline; SUSPICIOUS (structural credential material — JSON/YAML/TOML/
  dotenv credential keys, bare token prefixes, base64/encoded material,
  URLs with userinfo, shell credential flags, environment secret
  references, authorization headers/Bearer) is always elevated to HIGH so a
  human approval is required and auto-apply is impossible; OPAQUE content
  (control characters / unparseable) yields UNKNOWN so `RiskPolicy` DENYs
  it. No new `RiskLevel` enum value was added; the existing
  UNKNOWN->DENY and HIGH/CRITICAL->approval model is sufficient. Path
  signals were extended to backup/temp suffixes, hidden credential files,
  credential directories and production-env naming. Trivial assignments
  (`self.token = None`, `count = 3`, `os.environ["HOME"]`) stay benign so
  ordinary patches are not unnecessarily elevated.
- **Rationale:** the MISSION-018 audit demonstrated (with live probes) that
  the previous "not detected = safe" LOW baseline let the documented
  evasion classes auto-apply in GOVERNED mode without approval. Fail-closed
  means unknown/uncertain security input must never silently auto-apply;
  HIGH (approval) and UNKNOWN (DENY) are both acceptable outcomes. Adding
  only more regexes without fixing the baseline assumption would have left
  the class of "unrecognized" content unsafe.
- **Consequence:** LOW/MEDIUM auto-apply is retained but its security
  assumption is now explicit: it applies only to content positively
  classified as SAFE, bounded by (1) expanded suspicion detection, (2)
  OPAQUE->UNKNOWN fail-closed, (3) path-scope enforcement, (4)
  verification+rollback, (5) the store-backed apply boundary that
  re-classifies the patch. MISSION-014 approval authority and RECOVERY
  behavior are untouched.
- **Evidence:** `simulation/security/risk_engine.py`,
  `simulation/security/risk_policy.py`, `tests/risk_regression_test.py`,
  `tests/risk_pipeline_test.py`, adversarial corpus A37-A50; full suite
  579 passed / 10 skipped.

## D-030 — RECOVERY never bypasses the approval boundary; the apply boundary fails closed without an authority (MISSION-018B)
- **Status:** ACCEPTED, **VERIFIED** — MISSION-018B (2026-08-13).
- **Decision:** `ApplyAuthorization.authorize` no longer returns `True`
  when `approval_store is None`. The risk level is recomputed
  deterministically at the apply boundary and LOW/MEDIUM applies are
  authorized on the typed-decision + fingerprint contract; every
  HIGH/CRITICAL/UNKNOWN apply now requires a store-verified, single-use
  approval binding, and **a missing approval store is itself a denial**.
  This makes the apply boundary the narrowest enforcement point for every
  runtime path, including the bounded RECOVERY mode: a gate-off assembly or
  `agent_run.py --recovery` can no longer mutate a HIGH/CRITICAL/UNKNOWN
  patch without an approval authority. Each recovery retry is an
  independent PatchProposal that flows through risk classification, the
  approval stage and the store-backed apply boundary; attempt binding
  prevents an older attempt's approval from authorizing a new patch.
- **CLI semantics:** `agent_run.py --recovery` now wires the risk gate +
  approval store + ledger (no interactive gateway). RECOVERY means
  "bounded autonomous retry within a pre-authorized scope": LOW/MEDIUM
  auto-apply with rollback; HIGH/CRITICAL/UNKNOWN fail closed unless a
  pre-granted ledger approval exists. GOVERNED additionally wires the
  interactive `ConsoleApprovalGateway` so an operator can approve on the
  spot. PROPOSAL_ONLY stays mutation-free.
- **Rationale:** the MISSION-018 live audit demonstrated the
  `if self.approval_store is None: return True` path allowed RECOVERY to
  mutate HIGH/CRITICAL patches without any risk or approval evaluation.
  The retry budget is an availability/DoS bound, never a substitute for
  human authorization.
- **Consequence:** MISSION-014's approval authority (fingerprint/path/
  action/attempt/risk/object-identity binding, single-use, expiry) is
  preserved and now also enforced for ungoverned/gate-off assemblies;
  MISSION-018A's fail-closed risk classification is preserved; bounded
  retry (cap 3, duplicate-fingerprint stop, verification-only retry,
  terminal non-verification failures) is unchanged.
- **Evidence:** `simulation/agent/apply/apply_authorization.py`,
  `agent_run.py`, adversarial corpus A51-A65; full suite 594 passed / 10
  skipped.

## D-031 — One deterministic governance authority: `GovernanceEvaluator` (MISSION-019)
- **Status:** ACCEPTED, **VERIFIED** — MISSION-019 (2026-08-13).
- **Decision:** a single `GovernanceEvaluator`
  (`simulation/security/governance_evaluator.py`) wraps one `RiskEngine`
  + one `RiskPolicy` and is the ONLY risk authority consumed by the
  three governed layers — the pipeline gate
  (`WorkerActionPipeline`), the approval console
  (`ConsoleApprovalGateway`) and the apply boundary
  (`ApplyAuthorization`). `WorkerActionPipeline._bind_approval_authority`
  rebinds the apply executor's authorization to the pipeline's exact
  evaluator (engine identity, not a fresh default), so a caller-wired
  custom engine can never drift between the pipeline and the boundary.
  The apply boundary keeps its independent fail-closed checks (typed
  `ControllerDecision`, `approved is True`, fingerprint, store-backed
  `authorize_apply`) — a single evaluator does NOT mean the boundary
  stops checking; it means the *same* engine/policy is consulted.
- **Rationale:** MISSION-014 documented the drift risk of separately
  constructed engines; the MISSION-019 audit ranked triple
  risk-recomputation divergence as a top structural risk.
- **Consequence:** MISSION-018A (SAFE/SUSPICIOUS/OPAQUE) and MISSION-018B
  (store-less HIGH/CRITICAL/UNKNOWN => DENY) semantics are unchanged;
  the evaluator only fixes *which* engine/policy is consulted.
- **Evidence:** `tests/governance_evaluator_test.py` (engine-identity
  binding + end-to-end custom-engine HIGH path), corpus A71.

## D-032 — Apply-outcome journal + detect-only startup reconciliation (MISSION-019)
- **Status:** ACCEPTED, **VERIFIED** — MISSION-019 (2026-08-13).
- **Decision:** `ApplyOutcomeJournal`
  (`simulation/agent/apply/apply_outcome_journal.py`) is an append-only,
  hash-chained, secret-safe (content-hash-only) record of the apply
  lifecycle: INTENT -> APPLY_STARTED -> APPLIED | APPLY_FAILED ->
  VERIFIED | ROLLBACK_STARTED -> ROLLED_BACK | ROLLBACK_FAILED. Writes
  are validated against the state machine; `load()` fails closed on any
  corruption / out-of-order / duplicate transition. It is wired through
  `ApplyExecutor` + `ApplyVerifyPipeline` + `build_recovery_agent` +
  `agent_run.py` (--apply-journal). `ReconciliationEngine`
  (`simulation/agent/recovery/startup_reconciliation.py`) is **detect
  only**: after a restart it classifies every intent, inspects in-scope
  files against the journaled content hashes, and flags orphaned
  mutations and consumed approvals without a terminal outcome. It never
  writes a file and never re-authors an apply — repairing an orphan is
  a mutation and therefore requires a separate, explicit authorization
  decision (no "recovery exists" authorization bypass).
- **Rationale:** the audit showed the file mutation and the evidence
  event are not transactional; a crash between them left a mutation with
  no durable record. The journal closes that audit gap.
- **Consequence:** the journal is durable outcome evidence, never an
  authorization input (D-012 preserved); approval single-use, the apply
  boundary and bounded recovery are unchanged.
- **Evidence:** `tests/apply_outcome_journal_test.py`,
  `tests/startup_reconciliation_test.py`, `tests/fault_injection_test.py`
  (all seven crash windows), corpus A66-A70.

## D-033 — Atomic snapshot writes (MISSION-019)
- **Status:** ACCEPTED, **VERIFIED** — MISSION-019 (2026-08-13).
- **Decision:** `SnapshotStore.save` writes to a temp file, flushes +
  fsyncs, then `os.replace` over the target (tempfile + replace, same
  pattern as `FileApplier`), so a crash mid-write leaves either the old
  snapshot or the fully-written new one. Recovery's existing
  "unverifiable snapshot => fall back to full replay" semantics are
  unchanged.
- **Rationale:** the previous `open("w")` write could truncate the
  snapshot on a crash; recovery handled it safely, but the corruption
  window is now removed at the source.
- **Evidence:** `tests/fault_injection_test.py::test_window7_snapshot_write_crash_preserves_old_snapshot`.

## D-034 — Verification evidence redacted before it reaches the LLM (MISSION-019)
- **Status:** ACCEPTED, **VERIFIED** — MISSION-019 (2026-08-13).
- **Decision:** `WorkerAgent._format_evidence_line` routes verification
  stdout/stderr through `secret_policy.sanitize_for_llm` (redaction +
  length bound) before embedding it into the next retry prompt. This is
  a heuristic mitigation, not a claim that untrusted output is safe.
- **Rationale:** a failed test can print a secret value; the previous
  code fed it verbatim into the next LLM prompt.
- **Evidence:** `tests/secret_retry_boundary_test.py`, corpus A72.

## Open Decisions

- **Recovery by default?** Making `--recovery` the default in
  `agent_run.py` is deliberately unresolved (MISSION-004 remaining work).
- **Risk gate default-on?** Resolved for MISSION-011 and re-confirmed for
  MISSION-012/017: the gate stays an explicit opt-in (D-021/D-022). A
  human-approval UX now exists (MISSION-017), so default-on has no missing
  implementation dependency; whether it becomes default-on in the shipped
  assembly is a productization decision. **UNKNOWN.**
- **Human-approval UX:** resolved for the CLI by MISSION-017 (D-028); an
  async/API or web approval channel remains out of scope.
  **RESOLVED (CLI).**
