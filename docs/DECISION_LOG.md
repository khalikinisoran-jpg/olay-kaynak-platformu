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
  which depends on the `approval_store` contract that has no implementation
  (MISSION-012). Wiring the gate into the shipped assembly would silently
  hard-block every HIGH/CRITICAL patch with no resolution path. Keeping it
  opt-in preserves backward compatibility, does not weaken any security
  boundary, and lets MISSION-012 re-evaluate default-on when an approval
  store exists.

---

## Open Decisions

- **Recovery by default?** Making `--recovery` the default in
  `agent_run.py` is deliberately unresolved (MISSION-004 remaining work).
- **Risk gate default-on?** Resolved for MISSION-011: the gate stays an
  explicit opt-in (D-021). Whether it becomes default-on in the shipped
  assembly once an `ApprovalStore` exists is deferred to MISSION-012.
- **MISSION-012 approval store:** interface exists; implementation and
  human-approval UX undefined. **UNKNOWN.**
