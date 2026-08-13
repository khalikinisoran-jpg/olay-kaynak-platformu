# SECURITY_MODEL.md

Canonical security model of the implemented worker action pipeline and
event-sourcing core, branch `worker-action-pipeline` @ `a8de82e`
(2026-08-13; risk-layer status refreshed by the MISSION-011 close-out on
2026-08-12, MISSION-012/013/014 close-outs on 2026-08-12, the
MISSION-016 gap-closure hardening on 2026-08-12, the MISSION-017
productization & human-approval additions on 2026-08-13, the
MISSION-018A risk-boundary hardening on 2026-08-13, and the MISSION-018B
recovery-authorization hardening on 2026-08-13). Every claim
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
  The boundary recomputes the patch risk deterministically and requires a
  store-verified, single-use approval binding for every
  HIGH/CRITICAL/UNKNOWN apply; **a missing approval store is itself a
  denial** (MISSION-014/018B), so no runtime path — including the bounded
  RECOVERY mode or a gate-off assembly — can mutate a HIGH/CRITICAL/UNKNOWN
  patch without an approval authority. LOW/MEDIUM applies are authorized on
  the typed-decision + fingerprint contract because MISSION-018A ensures
  only positively-classified non-suspicious content reaches LOW/MEDIUM.
  **VERIFIED** — controller_decision_test.py, approval_boundary_test.py
  (MISSION-014 A/B/O), adversarial corpus A51-A65.
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
- **RECOVERY never bypasses the approval boundary (MISSION-018B):** the
  apply authorization boundary recomputes the patch risk and requires a
  store-verified approval for every HIGH/CRITICAL/UNKNOWN apply; a missing
  approval store is itself a denial, so a gate-off assembly or
  `agent_run.py --recovery` cannot mutate a HIGH/CRITICAL/UNKNOWN patch
  without an approval authority. Every retry is an independent
  PatchProposal with its own risk + approval evaluation; attempt binding
  prevents an older attempt's approval from authorizing a new patch.
  `agent_run.py --recovery` now wires the risk gate + approval store +
  ledger (no interactive gateway): LOW/MEDIUM auto-apply with rollback,
  HIGH/CRITICAL/UNKNOWN fail closed unless a pre-granted ledger approval
  exists. The retry budget never substitutes for human authorization.
  **VERIFIED** — adversarial corpus A51-A65, live probes.

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

## 7a. Risk Engine Fail-Closed Content Classification (MISSION-018A)

**Implementation:** `simulation/security/risk_engine.py` (MISSION-018A).

Security principle: **`not detected` is never treated as `safe`.** The
engine classifies content into three states before producing a level:

- **SAFE** -> plain, simple content with no credential-like, encoded or
  opaque material. Only SAFE content may keep the LOW/MEDIUM baseline that
  `RiskPolicy` auto-applies.
- **SUSPICIOUS** -> structural credential material, elevated to HIGH so a
  human approval is required and auto-apply is impossible: credential-key
  assignments in JSON/YAML/TOML/dotenv/INI/connection-string form (incl.
  quoted keys like `{"password": "x"}` and part-numbered keys like
  `token_part1`), bare token prefixes (`sk-`, `ghp_`, `gho_`, `ghs_`,
  `xox*`, `AKIA`, `ya29.`, JWT `eyJ`, `AIza`, `SG.`), base64/encoded
  material, URLs with userinfo (`user:pass@`), shell credential flags
  (`-u`, `--password`, `--token`), environment secret references
  (`os.environ["SECRET_KEY"]`, `process.env.API_TOKEN`, `${SECRET_KEY}`),
  and authorization headers / Bearer / Basic tokens.
- **OPAQUE** -> content that cannot be analyzed as plain text (control
  characters other than tab/newline/CR). Yields UNKNOWN so `RiskPolicy`
  DENYs it with no approval and no apply.

Path hardening (all -> HIGH): backup/temp suffixes (`.bak`, `~`, `.orig`,
`.swp`, ...), hidden credential files (`.creds`, `.credentials`, `.aws`,
`.azure`, `.gcloud`, `.pgpass`, `.kubeconfig`, ...), credential
directories (`secrets/`, `credentials/`, `token(s)/`, `keys/`, `certs/`,
`private/`, `auth/`, `ssh/`, `pki/`, `vault/`, ...) and production-env
naming (`prod`, `staging`, `uat`, `preprod`, `pre-prod`).

Trivial credential assignments stay benign (`self.token = None`,
`count = 3`, `os.environ["HOME"]`, `tokenizer = Tokenizer()`), so ordinary
patches are not unnecessarily elevated. **VERIFIED** —
`tests/risk_regression_test.py` (MISSION-018A corpus), `tests/risk_pipeline_test.py`
(suspicious content requires approval / opaque content fails at the risk
stage / trivial assignments still auto-apply), adversarial corpus A37-A50.

**STATUS: VERIFIED (MISSION-018A). The gate stays DEFAULT OFF; the fix
closes the auto-apply path for the audited evasion classes and adds an
OPAQUE -> UNKNOWN fail-closed path.**

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
- **LOW/MEDIUM security assumption (MISSION-018A):** auto-apply for
  LOW/MEDIUM is safe only because `RiskEngine` classifies content into
  SAFE / SUSPICIOUS / OPAQUE before a level is produced; SUSPICIOUS is
  always elevated to HIGH so it never reaches this automatic path, and
  OPAQUE yields UNKNOWN which is DENIED here. `not detected` is never
  treated as `safe`. False negatives are bounded by (1) the expanded
  structural suspicion detection, (2) the OPAQUE -> UNKNOWN fail-closed
  path, (3) worker/apply path-scope enforcement, (4) deterministic
  verification with rollback on failure, and (5) the store-backed apply
  boundary that re-classifies the patch before any write. **VERIFIED** —
  `tests/risk_regression_test.py` (benign negatives stay LOW/MEDIUM),
  `tests/risk_pipeline_test.py`, adversarial A50.
- **STATUS: VERIFIED (MISSION-011 / MISSION-018A).**

## 8a. Human Approval Boundary

**Implementation:** `simulation/agent/approval/` (MISSION-012/014).

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

## 8b. Interactive CLI Human-Approval Interface (MISSION-017)

**Implementation:** `simulation/agent/approval/approval_console.py`.

- A HIGH/CRITICAL request is rendered as a `PendingApprovalRequest` from
  the real `PatchProposal` + `RiskAssessment`; the renderer shows patch
  fingerprint, path, action, risk level + context, attempt, expiry,
  authorizer and evidence reference — never patch old/new content.
  **VERIFIED** — `tests/approval_console_test.py`
  (render shows all required fields; render never contains patch content).
- `ConsoleApprovalGateway.request_approval` is consulted by the pipeline
  only when no valid stored approval exists. It recomputes the risk with
  the system `RiskEngine` and refuses (`None`) when the pipeline-provided
  risk differs from the recomputed one, so a downgraded displayed risk
  cannot reach the human. **VERIFIED** —
  `tests/approval_console_test.py::test_console_gateway_refuses_downgraded_risk_display`.
- On explicit human approve, the gateway grants through `ApprovalStore`
  and the pipeline re-consumes the approval via `find_valid(patch=...)`
  (object-identity binding + single-use preserved), so displayed ==
  granted == applied by construction; any substitution (path/patch/action/
  risk) fails closed downstream. **VERIFIED** —
  `tests/approval_console_test.py` (wrong path / wrong patch / risk
  downgrade), corpus A33/A34.
- Fail-closed decision: only explicit approve phrases grant; deny, EOF and
  unrecognized input return `None` and never produce an approval.
  **VERIFIED** — `tests/approval_console_test.py`
  (deny / EOF / unrecognized input). A fake gateway returning an Approval
  the store never granted, or returning dict metadata, fails closed.
  **VERIFIED** — corpus A31, `test_console_gateway_rejects_non_approval_return`.
- The console never becomes an authority: the grant still flows through
  the store `find_valid`/`authorize_apply`, and agent-controlled approval
  metadata is never consulted. Evidence/ledger never contain patch content
  or secret values. **VERIFIED** — `tests/approval_console_test.py`
  (ledger/render/evidence no-leak tests).
- **STATUS: VERIFIED (MISSION-017).**

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

## 12. Rollback / Recovery Integrity (MISSION-016)

- Verification FAIL after a successful apply triggers a rollback to the
  exact pre-apply content via `ApplyExecutor.rollback` ->
  `FileApplier.restore` (canonical path, atomic tempfile+replace,
  read-back verified). **VERIFIED** — `tests/rollback_test.py`,
  `tests/apply_verify_pipeline_test.py`, corpus A21.
- A rollback failure is terminal (`FAILURE_ROLLBACK`); the bounded recovery
  loop never retries on an unknown/corrupted state. **VERIFIED** —
  `tests/rollback_test.py`, corpus A22.
- Retry after a rollback works from the clean pre-apply state: no
  cumulative modifications across attempts. **VERIFIED** —
  `tests/rollback_test.py`, `tests/runtime_governed_integration_test.py`,
  updated `tests/worker_evidence_test.py`.
- Rollback outcomes are recorded as `WorkerRollbackSucceeded` /
  `WorkerRollbackFailed` evidence events (secret-safe payloads).
  **VERIFIED** — `tests/rollback_test.py`.
- `WorkerActionPipeline` classifies a failed rollback as `FAILURE_ROLLBACK`
  (new stage) so callers can distinguish it from a plain verification
  failure. **VERIFIED** — `tests/rollback_test.py`.

## 13. Approval Durability (MISSION-016)

- `ApprovalLedger` appends hash-chained grant/consumed/applied records;
  `ApprovalStore` reloads authorization state from it on construction.
  **VERIFIED** — `tests/approval_durability_test.py`.
- A consumed or applied approval stays consumed/applied after a process
  restart (single-use survives restart). **VERIFIED** —
  `tests/approval_durability_test.py`, corpus A23.
- Corrupted, malformed or hash-broken ledger state raises `RuntimeError`
  (fail-closed; the store refuses to operate on corruption).
  **VERIFIED** — `tests/approval_durability_test.py`, corpus A24.
- Evidence events remain evidence-only (D-012 / MISSION-014 test_m); the
  ledger is a separate authorization-state file, not the evidence stream.
  **VERIFIED** — `tests/approval_boundary_test.py::test_m_*`.
- Object-identity approval binding is in-memory by nature and is re-bound
  on the next `find_valid(patch=...)` after a reload. **INFERRED**
  (documented limitation).

## 14. Event Store & Snapshot Integrity (MISSION-016)

- Appends are O(1) (cached chain head), serialized by a per-instance lock
  (thread-safe same-store appends) and fsynced; the store is the sequence
  authority (`next_sequence`). **VERIFIED** —
  `tests/event_store_concurrency_test.py`, corpus A28.
- Snapshot `content_hash` is verified on recovery; an unverifiable or
  inconsistent snapshot (e.g. `last_sequence` exceeding the event count) is
  not trusted — recovery falls back to a full replay from the
  chain-verified event log. **VERIFIED** — `tests/snapshot_integrity_test.py`,
  corpus A29.
- Event-chain corruption still raises `RuntimeError` (fail-closed; state
  cannot be rebuilt from unverifiable events). **VERIFIED** —
  `tests/snapshot_integrity_test.py`, corpus A11.
- Writes are atomic (tempfile + fsync + `os.replace`, permissions
  preserved); a crash leaves either the old or the fully-written new file,
  never a truncated mix. **VERIFIED** — `tests/patch_integrity_test.py`,
  corpus A08b/A21. Multi-process writers on one store file remain
  unsupported. **VERIFIED** (documented).

## 15. Verification Hardening (MISSION-016)

- A default timeout (120s) applies so a hanging verification cannot block
  the runtime; an explicit `timeout` still wins. **VERIFIED** —
  `tests/verification_executor_test.py`.
- pytest exit code 5 ("no tests collected") is FAIL, never PASS: a
  neutered or empty test target cannot be reported as verification
  success. **VERIFIED** — `tests/verification_executor_test.py`, corpus A27.
- `PYTHONPYCACHEPREFIX` redirects the verification subprocess bytecode
  cache out of the tree so compileall/pytest do not mutate the repository.
  **VERIFIED** — `tests/verification_executor_test.py`.

## 16. Secret / Prompt-Injection Boundary (MISSION-016)

- Secret files (`.env`, PEM keys, credential files) are never read into the
  LLM analyzer; the worker marks them `skipped_secret`.
  **VERIFIED** — `tests/secret_boundary_test.py`, corpus A25.
- Obvious inline secret values are redacted before content reaches the
  analyzer; proposals referencing the `[REDACTED]` marker are rejected.
  **VERIFIED** — `tests/secret_boundary_test.py`, corpus A26.
- The analyzer prompt marks file content and evidence text as UNTRUSTED
  DATA (never instructions). **VERIFIED** —
  `tests/secret_boundary_test.py`.
- Mitigation boundary: secret redaction and prompt-injection resistance are
  heuristics, not proofs; a missed pattern could still leak or steer.
  **VERIFIED** (documented) — not a completeness claim.

## 17. Runtime Governance Path (MISSION-016)

- `agent_run.py --governed` is the first shipped path that reaches the full
  risk/approval/authorization boundary. HIGH/CRITICAL/UNKNOWN fail closed
  without a valid approval; LOW/MEDIUM auto-apply with rollback on
  verification failure. **VERIFIED** — `tests/runtime_governed_integration_test.py`
  (11 tests: default proposal-only, DENY without approval, HIGH/CRITICAL
  ALLOW, wrong patch/path/risk DENY, single-use across runs, rollback,
  evidence, restart durability).
- The default runtime remains proposal-only and ungoverned; no security
  boundary was loosened. **VERIFIED** — `tests/worker_runtime_test.py`.

## 17a. Runtime Modes (MISSION-017)

- Three deterministic runtime modes exist through the existing assembly
  (no new abstraction): PROPOSAL_ONLY (`Agent(kernel)`, no pipeline/apply),
  RECOVERY (`build_recovery_agent`, bounded retry + authorization boundary
  ACTIVE), and GOVERNED (`build_recovery_agent` with risk_engine +
  risk_policy + store-backed approval + interactive gateway). Mode
  selection is deterministic; the gate never activates with only one risk
  component. **VERIFIED** — `tests/runtime_mode_test.py` (12 tests).
- **RECOVERY authorization boundary (MISSION-018B):** the apply boundary
  recomputes risk and DENIES every HIGH/CRITICAL/UNKNOWN apply that lacks a
  store-verified approval, even when the pipeline risk gate is off and no
  approval store is wired. `agent_run.py --recovery` now wires the risk
  gate + approval store + ledger so HIGH/CRITICAL/UNKNOWN fail closed
  unless a pre-granted ledger approval exists; LOW/MEDIUM auto-apply with
  rollback on verification failure and bounded retry. There is no
  interactive prompt in RECOVERY (that is GOVERNED's
  `ConsoleApprovalGateway`); the retry budget never substitutes for human
  authorization. **VERIFIED** — adversarial corpus A51-A65, live probes.
- `agent_run.py --governed` wires the interactive CLI approval gateway
  (`ConsoleApprovalGateway`), so a HIGH/CRITICAL proposal without a valid
  stored approval is presented to the operator for approve/deny; deny/EOF
  fail closed, the grant flows through the store. **VERIFIED** —
  `tests/approval_console_test.py`.

## 18. Adversarial Tests

`tests/security/adversarial_corpus_test.py` (MISSION-008, extended by
MISSION-013 to A13-A20, by MISSION-016 to A21-A30 and by MISSION-017 to
A31-A36): summary-gated — the final summary test fails the suite if any
recorded entry failed.
**VERIFIED** — all PASS on 2026-08-13 (69 passed, 1 symlink-dependent skip
in the normal suite; MISSION-018A added A37-A50, MISSION-018B added
A51-A65). MISSION-016 records: A21 rollback success, A22
rollback failure terminal, A23 restart replay denial, A24 corrupted ledger
fail-closed, A25 secret-file skip, A26 redaction, A27 empty-test-not-pass,
A28 concurrent append consistency, A29 snapshot tampering not trusted,
A30 direct FileApplier scope enforcement. MISSION-017 records: A31 fake
approval UI (hostile gateway returns an unbound Approval), A32 forged
operator identity is not a boundary, A33 console display/apply path
substitution denied, A34 console risk downgrade denied, A35
console-granted approval single-use (replay impossible), A36 governed
without allowed-path fails closed.

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
| A31 | Fake approval UI (gateway returns an Approval the store never granted) | Pipeline re-consumption via store | DENY |
| A32 | Forged operator identity (authorizer field) | Binding still authorizes; identity informational | ALLOW (binding correct) |
| A33 | Console display/apply path substitution | Approval path/fingerprint binding | DENY |
| A34 | Console risk downgrade (HIGH grant for CRITICAL patch) | Approval risk-level binding | DENY |
| A35 | Console-granted approval replay | Single-use find_valid consumption | DENY on replay |
| A36 | Governed mode with empty allowed-path scope | Worker fail-closed (no mutation scope) | DENY |
| A37 | JSON credential (`{"password": ...}`) previously auto-applied as LOW | RiskEngine HIGH -> approval required | DENY |
| A38 | Bare token (`sk-...`) previously auto-applied as LOW | RiskEngine HIGH -> approval required | DENY |
| A39 | Base64/encoded secret previously auto-applied as LOW | RiskEngine HIGH -> approval required | DENY |
| A40 | URL-embedded credential (`user:pass@`) previously auto-applied | RiskEngine HIGH -> approval required | DENY |
| A41 | Shell credential flag (`-u user:pass`) previously auto-applied | RiskEngine HIGH -> approval required | DENY |
| A42 | Environment secret reference (`os.environ['SECRET_KEY']`) | RiskEngine HIGH -> approval required | DENY |
| A43 | Authorization-header construction in source previously MEDIUM | RiskEngine HIGH -> approval required | DENY |
| A44 | Fragmented secret (`token_part1`/`token_part2`) | RiskEngine HIGH -> approval required | DENY |
| A45 | Backup/temp path (`app.py.bak`) previously LOW | RiskEngine HIGH -> approval required | DENY |
| A46 | Hidden credential file (`.creds`) previously LOW | RiskEngine HIGH -> approval required | DENY |
| A47 | Production-env naming (`prod.yaml`) previously LOW | RiskEngine HIGH -> approval required | DENY |
| A48 | `secrets/` directory with benign filename previously LOW | RiskEngine HIGH -> approval required | DENY |
| A49 | OPAQUE content (control characters) unclassifiable | UNKNOWN -> policy DENY at risk stage | DENY |
| A50 | Trivial credential assignment (`self.token = None`) | benign LOW auto-apply preserved (positive control) | ALLOW |
| A51 | Attempt 1 HIGH approved + verify FAIL; attempt 2 HIGH patch without a new approval | new patch = new approval; DENY at approval stage | DENY |
| A52 | Attempt 1 LOW; attempt 2 CRITICAL; attempt-1 approval reused | attempt binding; new risk needs new approval | DENY |
| A53 | Attempt 1 HIGH approved; attempt 2 LOW must not inherit the old HIGH approval | independent evaluation; old approval single-use consumed; replay DENY | ALLOW (LOW) / DENY (replay) |
| A54 | Same metadata but a different PatchProposal object | object-identity binding not bypassed by recovery | DENY |
| A55 | Same fingerprint replay (find_valid + apply) | single-use at lookup and at apply | DENY |
| A56 | Attempt-2 patch authorized with attempt-1 approval_id | approval_id bound to patch A | DENY |
| A57 | Expired approval for the retry attempt | expired approval unusable | DENY |
| A58 | Retry patch UNKNOWN (opaque) after a MEDIUM attempt | DENY at risk stage; no approval conversion | DENY |
| A59 | OPAQUE retry carries a pre-granted HIGH approval | UNKNOWN never converts to approval; risk stage DENY | DENY |
| A60 | Recovery assembly with no approval store drives a HIGH patch | apply boundary DENY; no write | DENY |
| A61 | HIGH retry without approval despite a 3-attempt budget | budget never grants authorization | DENY |
| A62 | Attempt 2 HIGH with a fresh approval granted for attempt 2 | new patch = new approval; ALLOW | ALLOW |
| A63 | Three HIGH attempts, each with its own approval, FAIL FAIL PASS | bounded retry preserved when authorized | ALLOW |
| A64 | HIGH without approval (approval denial is non-verification) | terminal; no retry | DENY |
| A65 | Same HIGH patch proposed again on retry | duplicate fingerprint stops retry | DENY |
| A66 | Corrupt apply journal (duplicate intent) | fail-closed load | REJECTED |
| A67 | Crash after APPLIED (no verify): orphaned mutation on disk | detected by reconciliation | DETECTED |
| A68 | Duplicate outcome (second VERIFIED) for one apply intent | single-use outcome | REJECTED |
| A69 | VERIFIED outcome recorded before APPLIED | invalid transition | REJECTED |
| A70 | One approval_id reused across two apply intents | reconciliation anomaly | FLAGGED |
| A71 | Custom risk engine wired to pipeline must be the exact engine at the apply boundary | single authority (identity bound) | NO DRIFT |
| A72 | Verification stdout with a secret value fed to the next LLM prompt on retry | redacted before prompt | REDACTED |

**NOT covered by the corpus (UNVERIFIED):** live-LLM end-to-end
apply/verify/recovery for the HIGH/CRITICAL approval path and
concurrency/multi-agent behavior. (Risk engine
behavior, the pipeline risk gate, human-approval boundary, the MISSION-014
store-backed apply authorization, the interactive CLI approval console
(MISSION-017, A31-A36), compile-only depth and
approval/policy substitution are now covered by `tests/risk_*.py`,
`tests/approval_console_test.py`, `tests/runtime_mode_test.py` and
`tests/approval_boundary_test.py`, MISSION-011/012/014/017.)

---

## 19. Single Governance Authority (MISSION-019)

**Implementation:** `simulation/security/governance_evaluator.py`
(`GovernanceEvaluator`, `GovernanceDecision`).

- The pipeline gate, `ConsoleApprovalGateway` and `ApplyAuthorization`
  now consume ONE `GovernanceEvaluator` wrapping one `RiskEngine` +
  one `RiskPolicy`. `WorkerActionPipeline._bind_approval_authority`
  rebinds the apply executor's authorization to the pipeline's exact
  evaluator (engine identity), so a caller-wired custom engine can never
  diverge between the pipeline and the boundary. **VERIFIED** —
  `tests/governance_evaluator_test.py` (engine-identity assertion),
  corpus A71.
- The apply boundary keeps its independent fail-closed checks (typed
  `ControllerDecision`, `approved is True`, fingerprint, store-backed
  `authorize_apply`); a single evaluator means the *same* engine/policy
  is consulted, not that the boundary stops checking. **VERIFIED**.
- MISSION-018A (SAFE/SUSPICIOUS/OPAQUE; `not detected` is never `safe`)
  and MISSION-018B (store-less HIGH/CRITICAL/UNKNOWN => DENY) are
  unchanged; the evaluator only fixes which engine/policy is consulted.
  **VERIFIED** — full risk + approval + recovery suites still pass.

## 20. Apply-Outcome Journal & Crash Consistency (MISSION-019)

**Implementation:** `simulation/agent/apply/apply_outcome_journal.py`,
`simulation/agent/recovery/startup_reconciliation.py`.

- Lifecycle: INTENT -> APPLY_STARTED -> APPLIED | APPLY_FAILED ->
  VERIFIED | ROLLBACK_STARTED -> ROLLED_BACK | ROLLBACK_FAILED.
  Append-only, hash-chained, secret-safe (content hashes only).
  **VERIFIED** — `tests/apply_outcome_journal_test.py`.
- `load()` fails closed on any corruption, hash break, unknown record
  type, unknown intent or out-of-order / duplicate transition.
  **VERIFIED** — corpus A66/A68/A69.
- Startup reconciliation is **detect-only**: it classifies intents,
  inspects in-scope files against journaled content hashes, and flags
  orphaned mutations and consumed approvals without a terminal outcome.
  It never writes a file and never re-authors an apply, so the approval
  boundary is never bypassed by "recovery exists". **VERIFIED** —
  `tests/startup_reconciliation_test.py`, `tests/fault_injection_test.py`
  (all seven crash windows), corpus A67/A70.
- **Crash windows closed for detection:** approval-consumed-without-apply,
  apply-start, apply-without-verify, verify-then-rollback-crash,
  rollback-complete-without-evidence, reducer failure, snapshot write
  crash (atomic). **VERIFIED** — `tests/fault_injection_test.py`.
- **Limitation (UNKNOWN by design):** auto-repair of orphaned mutations
  is NOT implemented — it is a filesystem mutation and therefore needs a
  separate, explicit authorization decision; until then, orphans are
  detected and reported only.

## 21. Kernel Reducer-Failure Semantics (MISSION-019, documented + tested)

- `Kernel.dispatch` order is append -> trace -> reducer
  (`simulation/core/kernel.py`). A reducer failure on a persisted event
  propagates; the event stays durably in the store while the live state
  diverges; restart replay re-applies the event and reproduces the same
  reducer failure (fail-closed, no silent divergence). **VERIFIED** —
  `tests/fault_injection_test.py::test_window6_*`.

## 22. Atomic Snapshots (MISSION-019)

- `SnapshotStore.save` writes temp + fsync + `os.replace`; a crash
  mid-write leaves the old or the fully-written new snapshot, never a
  truncated mix. Recovery's "unverifiable snapshot => full replay" is
  unchanged. **VERIFIED** —
  `tests/fault_injection_test.py::test_window7_*`.

## 23. Verification-Evidence Redaction (MISSION-019)

- Verification stdout/stderr is redacted and length-bounded
  (`secret_policy.sanitize_for_llm`) before it is embedded in the next
  LLM retry prompt (`WorkerAgent._format_evidence_line`). Heuristic
  mitigation, not a proof. **VERIFIED** —
  `tests/secret_retry_boundary_test.py`, corpus A72.

---

## Overall Security Posture

- Strong verified boundary for path scope, exact old_content, typed
  controller approval, fingerprint-bound apply, deterministic
  verification, bounded recovery, hash-chained evidence, fail-closed
  defaults, a tested system-derived risk layer
  (RiskLevel/RiskEngine/RiskPolicy, MISSION-011) hardened by MISSION-018A
  (SAFE / SUSPICIOUS / OPAQUE content classification; `not detected` is
  never treated as `safe`) and a tested, fingerprint-bound, single-use
  human approval boundary (Approval/ApprovalStore, MISSION-012) hardened
  at the apply boundary so that no duck-typed object, forged decision,
  agent-claimed approval id, replayed/expired approval, evidence-only
  record or object-substituted approval can authorize a write
  (MISSION-014).
- HIGH/CRITICAL risk is now enforced with a real approval path that fails
  closed on missing/malformed/expired/wrong/replayed approvals, never
  trusts agent- or proposal-contained approval metadata, and re-verifies
  the consumed approval binding at the apply boundary itself
  (MISSION-012/014, corpus A13-A20, boundary tests A–O). The risk gate
  remains an explicit opt-in, not default-on (D-021/D-022); MISSION-018B
  additionally makes the apply boundary fail closed without an approval
  authority, so RECOVERY and gate-off assemblies can never mutate
  HIGH/CRITICAL/UNKNOWN patches (corpus A51-A65).
- No production deployment exists; symlink-skip, live-LLM and
  concurrency/multi-agent behavior remain UNKNOWN outside this
  environment.
- MISSION-019 added a single governance authority (D-031) so the
  pipeline / console / apply boundary can never diverge on risk
  classification, an apply-outcome journal + detect-only reconciliation
  (D-032) so a mutation can never exist without a durable outcome
  record and orphans are detectable after restart, atomic snapshot
  writes (D-033), and verification-evidence redaction before the LLM
  (D-034). None of these loosens a prior boundary; the full suite
  (648 passed / 10 skipped) and the adversarial corpus (A01-A72) pass.
