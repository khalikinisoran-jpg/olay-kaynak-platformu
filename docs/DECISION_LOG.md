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

## Open Decisions

- **Recovery by default?** Making `--recovery` the default in
  `agent_run.py` is deliberately unresolved (MISSION-004 remaining work).
- **Risk gate default-on?** Resolved for MISSION-011 and re-confirmed for
  MISSION-012: the gate stays an explicit opt-in (D-021/D-022). Whether it
  becomes default-on in the shipped assembly once a human-approval UX
  exists is a productization decision. **UNKNOWN.**
- **Human-approval UX:** the `ApprovalStore` exists and is tested; the
  interactive flow for routing a HIGH/CRITICAL request to a human and back
  into `grant` is undefined. **OPEN.**
