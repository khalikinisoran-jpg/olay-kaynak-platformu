# SECURITY_MODEL.md

Canonical security model of the implemented worker action pipeline and
event-sourcing core, branch `worker-action-pipeline` @ `96ed72d`
(2026-08-11; risk-layer status refreshed by the MISSION-011 close-out on
2026-08-12). Every claim is classified VERIFIED (code + passing test),
INFERRED (reasoned from code, no direct test), or UNKNOWN (cannot be
determined). Complements docs/SECURITY_BASELINE.md (MISSION-005 audit).

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
- ApplyAuthorization requires `decision.approved is True` AND
  `decision.patch_fingerprint == patch.fingerprint()`
  (apply_authorization.py:18). **VERIFIED** — controller_decision_test.py
  (exact-True, fingerprint-match), worker_contract_test.py.
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
- **UNKNOWN:** behavior when the LLM provider is unavailable at runtime in
  the shipped default path (ProviderFactory.create raises ValueError if
  OPENROUTER_API_KEY missing; no graceful degradation test).

## 11. Adversarial Tests

`tests/security/adversarial_corpus_test.py` (MISSION-008): 17 test
functions / 15 records (A01-A12 + sub-cases), summary-gated — the final
summary test fails the suite if any recorded entry failed. **VERIFIED** —
all PASS on 2026-08-11.

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

**NOT covered by the corpus (UNVERIFIED):** live-LLM end-to-end
apply/verify/recovery. (Risk engine behavior, the pipeline risk gate,
human-approval boundary and compile-only depth are now covered by
`tests/risk_*.py`, MISSION-011.)

---

## Overall Security Posture

- Strong verified boundary for path scope, exact old_content, typed
  controller approval, fingerprint-bound apply, deterministic
  verification, bounded recovery, hash-chained evidence, fail-closed
  defaults, and a now-tested system-derived risk layer
  (RiskLevel/RiskEngine/RiskPolicy, MISSION-011).
- The largest remaining security-relevant gap is the human-approval
  boundary (MISSION-012): the `approval_store` contract is consumed by the
  pipeline but unimplemented, so HIGH/CRITICAL risk is enforced by
  fail-closed blocking until that exists. The risk gate is therefore an
  explicit opt-in, not default-on (D-021).
- No production deployment exists; symlink-skip and live-LLM behavior
  remain UNKNOWN outside this environment.
