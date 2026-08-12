# SECURITY_MODEL.md

Canonical security model of the implemented worker action pipeline and
event-sourcing core, branch `worker-action-pipeline` @ `f94c82b`
(2026-08-11; risk-layer status refreshed by the MISSION-011 close-out on
2026-08-12, the MISSION-012/013 close-out on 2026-08-12, and the
MISSION-014 authorization-boundary hardening on 2026-08-12). Every claim
is classified VERIFIED (code + passing test), INFERRED (reasoned from
code, no direct test), or UNKNOWN (cannot be determined). Complements
docs/SECURITY_BASELINE.md (MISSION-005 audit).

---

## 1. Path Scope

**Implementation:** `simulation/security/path_policy.py::PathPolicy`.

- R1 Input integrity: path and every allowed_paths entry must be a
  non-empty string without NUL bytes; empty/None scope fails closed
  (path_policy.py:131-210). **VERIFIED** — `tests/security/path_security_test.py`
  (empty path/scope, None, null byte, empty entry).
- R2 Canonicalization: `Path.resolve(strict=False)` + `os.path.normcase`
  before comparison (path_policy.py:219). **VERIFIED** — relative/absolute
  form equivalence test.
- R3 Traversal: any `..` component rejected up front (path_policy.py:212).
  **VERIFIED** — traversal tests at path, scope and patch-validator levels.
- R4 Containment: canonical target must equal or descend from an allowed
  entry (`_within`, path_policy.py:238). **VERIFIED** — exact match,
  descendant, sibling-out-of-scope, prefix-confusion tests.
- R5 Symlink/junction escape: resolved target leaving scope is rejected
  (path_policy.py:97,254). **VERIFIED** — symlink/junction escape tests;
  7 symlink tests SKIP where the OS denies symlink creation (junction
  variants pass on this Windows environment). **UNKNOWN** — behavior on
  OSes where symlinks require privileges beyond junction coverage.
- Write-through canonical target: `PathPolicy.resolve_target` returns the
  exact canonical form and `FileApplier` reads/writes through it
  (MISSION-006). **VERIFIED** — `tests/patch_integrity_test.py`
  (write-through in-scope symlink).

## 2. Patch Validation

**Implementation:** `simulation/agent/worker/patch_validator.py`.

- Only `modify` action accepted (patch_validator.py:10). **VERIFIED** —
  worker_contract_test.py, adversarial A05.
- Re-checks scope, file existence, file type, current-content ==
  `old_content`, and rejects no-op changes (old==new). **VERIFIED** —
  worker_contract_test.py (valid/stale/no-change/out-of-scope/empty scope).
- Scope is enforced again at the real write point (FileApplier), so a
  stale patch cannot be applied even if an earlier gate passed.
  **VERIFIED** — patch_integrity_test.py, adversarial A07.

## 3. Exact old_content

- Full-file exact match is required both at `PatchValidator.validate`
  (patch_validator.py:80) and at write time in `FileApplier.apply`
  (file_applier.py:87). Any divergence => DENY ("Patch is stale").
  **VERIFIED** — patch_integrity_test.py (concurrent modification, second
  stale patch), adversarial A07, worker_contract_test.py (rejects stale).
- Analyzer requires `old_text` to occur exactly once in file content
  (worker_agent.py:187, llm_code_analyzer.py:170). **VERIFIED** —
  structured_analysis_test.py, adversarial A06.

## 4. Apply Control

**Implementation:** `Controller`, `ApplyAuthorization`, `ApplyExecutor`,
`FileApplier`.

- Controller approves only `ValidationResult` with `valid is True` (strict
  identity); missing/malformed/unknown fails closed; message text never
  consulted (MISSION-007). **VERIFIED** — `tests/controller_decision_test.py`
  (13 tests).
- ApplyAuthorization requires a real `ControllerDecision` with
  `decision.approved is True` AND `decision.patch_fingerprint ==
  patch.fingerprint()` (apply_authorization.py:18); a duck-typed fake
  object is rejected by the type check, so an agent-controlled object with
  `approved=True` + matching fingerprint can no longer authorize apply.
  When the boundary is bound to the approval authority (risk gate
  enabled) it recomputes the patch risk deterministically and requires a
  store-verified, single-use approval binding for HIGH/CRITICAL/UNKNOWN
  applies (MISSION-014). **VERIFIED** — controller_decision_test.py,
  approval_boundary_test.py (MISSION-014 A/B/O).
- Apply is never active by default: `Agent(kernel)` has no pipeline; only
  `build_recovery_agent()` or `agent_run.py --recovery` wires apply.
  **VERIFIED** — `tests/worker_runtime_test.py`
  (test_default_agent_does_not_construct_action_pipeline,
  test_default_agent_runtime_is_proposal_only_no_apply_no_verify).
- Post-write read-back verifies written bytes == approved `new_content`;
  mismatch triggers bounded restore of `old_content` and FAIL
  (file_applier.py:116-142). **VERIFIED** — patch_integrity_test.py
  (corrupted write + restore), adversarial A08b.
- **LIMITATION:** restore is best-effort; write is not atomic against an
  adversarial concurrent writer (out of scope for single-process).
  **VERIFIED** (documented in MISSION-006).

## 5. Verification

**Implementation:** `simulation/agent/verify/verification_executor.py`,
`command_runner.py`, pipeline in `apply_verify_pipeline.py`.

- Verification runs ONLY after a successful apply; apply success is never
  verification success (apply_verify_pipeline.py:67). **VERIFIED** —
  apply_verify_pipeline_test.py, adversarial A08/A09.
- Deterministic commands as arg lists, `shell=False` (command_runner.py:38);
  no shell interpretation. **VERIFIED** — verification_executor_test.py
  (safe command args).
- PASS/FAIL derived from exit code 0, not from stdout text. **VERIFIED** —
  verification_executor_test.py (non-zero exit is fail).
- stdout/stderr/exit code/timed-out/error preserved in `VerificationEvidence`.
  **VERIFIED** — verification_executor_test.py.
- Timeout and process errors => FAIL (exit -1). **VERIFIED** —
  verification_executor_test.py (timeout, process failure).
- Verification depth: `verify` = compileall + pytest;
  `verify_python_compile` = compile only (added MISSION-011). Default
  `compile+tests` and the `compile`-only path are both covered by tests
  (MISSION-011: `tests/risk_pipeline_test.py` asserts the compile path calls
  `verify_python_compile` only, and that the policy-chosen depth reaches the
  pipeline). **VERIFIED.**
- Verification never modifies the target (it compiles the *applied* file).
  **VERIFIED** — verification_executor_test.py
  (test_verification_executor_does_not_modify_target).

## 6. Retry / Recovery

**Implementation:** `simulation/agent/recovery/bounded_recovery_engine.py`.

- Hard attempt cap of exactly 3; no caller value can raise it or produce a
  fourth attempt (`MAX_ATTEMPTS_CAP=3`, `_bounded_max_attempts`).
  **VERIFIED** — recovery_engine_test.py (t03, t11, t13, t21, adversarial A10).
- Retry only on verification FAIL; validator/controller/apply failures are
  terminal; worker/pipeline exceptions are terminal.
  **VERIFIED** — recovery_engine_test.py (t05, t06, t07, t14, t15).
- Duplicate patch fingerprints stop retries (no blind reapply).
  **VERIFIED** — recovery_engine_test.py (t09, t18).
- Attempt history is append-only; `RecoveryAttempt`/`RecoveryResult` are
  immutable evidence contracts. **VERIFIED** — recovery_engine_test.py (t10).
- Recovery is not active by default (opt-in assembly / `--recovery`).
  **VERIFIED** — recovery_engine_test.py (t16), agent_run.py.

## 7. Risk Engine

**Implementation:** `simulation/security/risk_engine.py` (MISSION-011).

- System-derived classification from observable signals: action
  (destructive => CRITICAL, non-modify => HIGH), security-sensitive /
  privilege-boundary / production-config path fragments, secret-file
  suffixes, executable-source suffixes, large change size, PEM blocks and
  secret-like assignments in new_content
  (risk_engine.py:9-302). **VERIFIED** — `tests/risk_engine_test.py`
  (30 tests, MISSION-011).
- Missing patch => `RiskLevel.UNKNOWN` (risk_engine.py:141).
  **VERIFIED** — `tests/risk_engine_test.py`.
- Missing/malformed/empty/non-string action => `RiskLevel.UNKNOWN`
  (fail-closed). **VERIFIED** — `tests/risk_engine_test.py`; a latent bug
  (missing action silently returned LOW because `max_level` is a no-op with
  UNKNOWN) was fixed in MISSION-011 so the fail-closed path reaches the
  policy DENY.
- Advisory LLM risk can only RAISE the level (most restrictive wins);
  invalid advisory input is dropped; UNKNOWN advisory is not applied;
  confidence is recorded only when numeric and never a decision input
  (risk_engine.py:303-329). **VERIFIED** — `tests/risk_engine_test.py`.
- Malformed non-action content (non-string old/new) does not crash and does
  not elevate (defensive; such input cannot pass the validator in practice).
  **VERIFIED** — `tests/risk_engine_test.py`.
- **STATUS: VERIFIED (MISSION-011). The gate is DEFAULT OFF and only
  explicit opt-in: it is not wired into the shipped assembly by default
  (D-021).**

## 8. Risk Policy

**Implementation:** `simulation/security/risk_policy.py` (MISSION-011).

- Missing/malformed assessment => DENY (`allowed=False`, UNKNOWN)
  (risk_policy.py:51-70). **VERIFIED** — `tests/risk_policy_test.py`
  (18 tests, MISSION-011).
- UNKNOWN => DENY, never auto-approvable (risk_policy.py:84).
  **VERIFIED** — `tests/risk_policy_test.py`.
- HIGH/CRITICAL => `requires_human_approval=True`, `allow_auto_apply=False`,
  `max_attempts=1`. **VERIFIED** — `tests/risk_policy_test.py`.
- LOW => auto-apply, max_attempts=3; MEDIUM => auto-apply, max_attempts=2
  (risk_policy.py:91-121). **VERIFIED** — `tests/risk_policy_test.py`.
- `max_attempts` from policy never exceeds the recovery hard cap of 3 by
  construction. **VERIFIED** — `tests/risk_policy_test.py`.
- **STATUS: VERIFIED (MISSION-011).**

## 8a. Human Approval Boundary

**Implementation:** `simulation/agent/approval/` (MISSION-012).

- `Approval` is a frozen, single-use authorization contract bound to patch
  fingerprint, path, action, risk level, attempt, authorizer and expiry.
  Construction is fail-closed: missing/empty/non-string fingerprint, path,
  action or authorizer, a non-HIGH/CRITICAL risk label, a non-positive or
  non-int attempt, and malformed timestamps all raise
  (approval.py `__post_init__`). **VERIFIED** —
  `tests/approval_boundary_test.py`
  (test_approval_construction_fails_closed_on_malformed_fields).
- `ApprovalStore.find_valid` requires the complete authorization context
  (missing fingerprint, path, action, risk level or attempt fails closed),
  returns the first granted, unexpired, unconsumed approval matching the
  full requested context, consumes it on success and binds it to the exact
  patch object when supplied (approval_store.py:104). A replay of the same
  approval => `None`. **VERIFIED** — tests/approval_boundary_test.py
  (replay/expiry/substitution/incomplete-context tests), corpus
  A13/A14/A15/A17/A18.
- `ApprovalStore.authorize_apply(approval_id, patch)` is the narrowest
  enforcement point: the apply boundary verifies the referenced approval
  was granted by this store, was released by `find_valid`, is bound to
  this exact patch object (object identity), is not expired, has not
  already authorized an apply, and matches fingerprint/path/action. On
  success it consumes the approval for apply (exactly once). **VERIFIED** —
  tests/approval_boundary_test.py (MISSION-014 A–O).
- The pipeline re-validates the returned object itself
  (`_approval_is_valid`, worker_action_pipeline.py): it must be a typed
  `Approval` whose fingerprint, path, action, risk level and attempt
  exactly match the current patch/risk/attempt, and it must not be
  expired. Missing, malformed (dict/object), substituted, downgraded or
  forged approvals => DENY at the approval stage (`failure_stage="approval"`),
  no apply, no verification. The store-backed apply authorization then
  re-verifies the consumed approval binding at apply time, so a forged
  `ControllerDecision`, an agent-claimed approval id, a replayed approval
  or an approval bound to a different patch object cannot reach the write
  path (MISSION-014). **VERIFIED** — tests/approval_boundary_test.py
  (malformed/forged/wrong-context + A–O tests), corpus A16/A19.
- Proposal-contained or agent-fabricated approval metadata is never
  consulted; only a validated `Approval` returned by the store can
  authorize a HIGH/CRITICAL patch (agent independence). **VERIFIED** —
  corpus A16/A20.
- Every grant is recorded as a `WorkerHumanApprovalGranted` event through
  the existing Kernel/event store (hash chain, sequence, snapshot, replay
  all apply); payloads are secret-safe (no patch content).
  **VERIFIED** — tests/approval_boundary_test.py
  (test_approval_grant_records_evidence_event,
  test_approval_grant_flows_through_real_kernel_hash_chain).
- The risk gate stays DEFAULT OFF / explicit opt-in (D-021/D-022); this
  boundary only activates when the caller wires `risk_engine` +
  `risk_policy` (+ optional `approval_store`) into the pipeline/assembly.
  **VERIFIED** — tests/approval_boundary_test.py
  (test_assembly_wires_approval_store_when_gate_enabled).
- **STATUS: VERIFIED (MISSION-012/014).**

## 9. Evidence / Integrity

**Implementation:** `EventStore`, `HashChain`, `HashVerifier`,
`WorkerEvidenceRecorder`.

- Append-only JSONL; each record carries `previous_hash`/`current_hash`
  (SHA-256 over the serialized record) (event_store.py:26-60).
  **VERIFIED** — hash_test.py, replay_test.py, adversarial A11.
- `HashVerifier.verify` recomputes the chain from GENESIS; any mutation
  breaks verification (hash_verifier.py:17). **VERIFIED** — adversarial A11
  (event tampering after dispatch detected), worker_evidence_test.py
  (hash-chain integrity after pipeline run).
- Worker evidence events are normal Events dispatched through Kernel, so
  sequence, hashing, snapshots and replay all apply
  (worker_evidence_recorder.py:7-25). **VERIFIED** — worker_evidence_test.py.
- Payload secret-safety: patch content and verification stdout/stderr never
  enter payloads; only fingerprints and status/exit code/failure reason.
  **VERIFIED** — worker_evidence_test.py
  (test_payloads_never_contain_patch_content_or_command_output).
- DecisionTrace mirrors steps but is in-memory; event log is the durable
  evidence. **VERIFIED** (documented design decision).
- Event store has no dedup; duplicate handling exists only at recovery
  level. **VERIFIED** (SECURITY_BASELINE.md finding G).

## 10. Fail-Closed Boundaries

- Default runtime proposal-only: no pipeline, no apply, no verify, no
  recovery. **VERIFIED** — worker_runtime_test.py (t16).
- Empty/None `allowed_paths` on WorkerTask => worker fails with
  "No allowed paths were provided." **VERIFIED** — worker_read_scope_test.py.
- Empty task `allowed_actions` = unconstrained (backward compatible);
  non-empty = default-deny for any required action not listed
  (worker_agent.py:262). **VERIFIED** — worker_read_scope_test.py (4 tests),
  adversarial A05b.
- WorkerAgent rejects analyzer returns that are not `AnalysisResult`
  (worker_agent.py:171). **VERIFIED** — structured_analysis_test.py.
- `AnalysisResult` construction raises on malformed values
  (analysis_result.py:50). **VERIFIED** — structured_analysis_test.py (41 tests).
- Controller fails closed on non-`ValidationResult` input
  (controller.py:22). **VERIFIED** — controller_decision_test.py.
- `WorkerEvidenceRecorder` rejects unknown event types
  (worker_events.py:59). **VERIFIED** — worker_evidence_test.py.
- HIGH/CRITICAL without a valid approval fails closed at the approval
  stage: missing approval store, missing grant, malformed (non-`Approval`)
  returned value, expired approval, wrong fingerprint/path/action/risk/
  attempt, or a replayed approval all => DENY (`failure_stage="approval"`),
  no apply, no verification. **VERIFIED** —
  tests/approval_boundary_test.py (48 tests), corpus A13-A20.
- The apply boundary is itself store-backed when the risk gate is enabled:
  a forged `ControllerDecision` (with or without a matching fingerprint),
  an agent-claimed approval id, an unconsumed grant id, evidence-only
  metadata, a replayed/expired approval, or an approval bound to a
  different patch object (identical metadata included) all fail closed at
  `ApplyAuthorization`/`ApprovalStore.authorize_apply` before any write
  (MISSION-014). **VERIFIED** — tests/approval_boundary_test.py (MISSION-014
  A–O).
- **UNKNOWN:** behavior when the LLM provider is unavailable at runtime in
  the shipped default path (ProviderFactory.create raises ValueError if
  OPENROUTER_API_KEY missing; no graceful degradation test).

## 11. Adversarial Tests

`tests/security/adversarial_corpus_test.py` (MISSION-008, extended by
MISSION-013): 25 test functions / 23 records (A01-A20 + sub-cases),
summary-gated — the final summary test fails the suite if any recorded
entry failed. **VERIFIED** — all PASS on 2026-08-12 (24 passed, 1
symlink-dependent skip in the normal suite). The MISSION-014
authorization-boundary hardening adds 17 deterministic boundary tests
(A–O) in `tests/approval_boundary_test.py` (48 tests total).

| ID | Attack | Boundary measured | Result |
|----|--------|-------------------|--------|
| A01 | Path traversal (`..`) | Path scope | DENY, no write |
| A02 | Absolute path outside scope | Path scope | DENY, no write |
| A03/A03b | Symlink / junction escape | Path scope | DENY, outside file untouched |
| A04 | Unauthorized path | Path scope | DENY |
| A05/A05b | Unauthorized action / allowed_actions | Action scope | DENY |
| A06 | Duplicate old_text | Analysis contract | REJECT, no proposal |
| A07 | Stale patch / concurrent modification | old_content exactness | DENY, current content intact |
| A08/A08b | Apply != verify; corrupted write | Apply/verify separation | FAIL + restore |
| A09 | Verification forgery | Verification source | verification only from executor |
| A10 | Retry budget (999 requested) | Recovery bound | hard cap 3 |
| A11 | Evidence tampering after dispatch | Hash chain | detected |
| A12/A12b | Fingerprint boundary / prefix confusion | Apply authorization | DENY |
| A13 | Approval replay (same approval twice) | Approval single-use | first ALLOW, second DENY |
| A14 | Approval substitution (approve A, replay for B) | Approval fingerprint binding | DENY |
| A15 | Risk-context substitution (HIGH approval for CRITICAL flow) | Approval risk binding | DENY |
| A16 | Forged dict approval metadata (hostile store) | Approval type/binding | DENY |
| A17 | Expired / stale approval | Approval expiry | DENY |
| A18 | Attempt substitution (attempt-1 approval at attempt 2) | Approval attempt binding | DENY |
| A19 | Path substitution (typed Approval, different path) | Pipeline-level binding check | DENY |
| A20 | Approval-gate bypass (no authority + proposal claims) | Agent independence | DENY |

**NOT covered by the corpus (UNVERIFIED):** live-LLM end-to-end
apply/verify/recovery and concurrency/multi-agent behavior. (Risk engine
behavior, the pipeline risk gate, human-approval boundary, the MISSION-014
store-backed apply authorization, compile-only depth and
approval/policy substitution are now covered by `tests/risk_*.py` and
`tests/approval_boundary_test.py`, MISSION-011/012/014.)

---

## Overall Security Posture

- Strong verified boundary for path scope, exact old_content, typed
  controller approval, fingerprint-bound apply, deterministic
  verification, bounded recovery, hash-chained evidence, fail-closed
  defaults, a tested system-derived risk layer
  (RiskLevel/RiskEngine/RiskPolicy, MISSION-011) and a tested,
  fingerprint-bound, single-use human approval boundary
  (Approval/ApprovalStore, MISSION-012) hardened at the apply boundary so
  that no duck-typed object, forged decision, agent-claimed approval id,
  replayed/expired approval, evidence-only record or object-substituted
  approval can authorize a write (MISSION-014).
- HIGH/CRITICAL risk is now enforced with a real approval path that fails
  closed on missing/malformed/expired/wrong/replayed approvals, never
  trusts agent- or proposal-contained approval metadata, and re-verifies
  the consumed approval binding at the apply boundary itself
  (MISSION-012/014, corpus A13-A20, boundary tests A–O). The risk gate
  remains an explicit opt-in, not default-on (D-021/D-022).
- No production deployment exists; symlink-skip, live-LLM and
  concurrency/multi-agent behavior remain UNKNOWN outside this
  environment.
