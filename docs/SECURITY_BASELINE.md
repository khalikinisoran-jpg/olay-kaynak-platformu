# Security Baseline Audit

MISSION-005 result. This document records the real code-level security
baseline extracted from the current repository on branch
`worker-action-pipeline`, with severity, evidence, existing tests, missing
tests and minimal fixes.

Classification vocabulary used throughout:

- **VERIFIED** — the behavior is real in code and backed by passing tests.
- **NOT REPRODUCED** — the behavior does not exist in current code/tests.
- **OPEN** — behavior exists but is not fully covered or is only partially
  mitigated.
- **UNKNOWN** — cannot be determined from available evidence.

---

## 1. Previously Reported Findings

### A) `test_apply_executor_is_disabled_by_default`

**Classification: NOT REPRODUCED (as named) — underlying property VERIFIED by different tests.**

The test `test_apply_executor_is_disabled_by_default` does not exist in the
repository (`git grep` over all `tests/**/*.py` finds no test with this name
and no `disabled` symbol anywhere).

The security property "apply is not active by default" **is** enforced and
covered, but by differently named tests:

- `tests/worker_runtime_test.py::test_default_agent_does_not_construct_action_pipeline`
  (line 230) — a default `Agent(kernel)` has `worker_pipeline is None`.
- `tests/worker_runtime_test.py::test_default_agent_runtime_is_proposal_only_no_apply_no_verify`
  (line 267) — a default agent run produces a proposal and never mutates the
  target file.
- `tests/worker_contract_test.py::test_apply_executor_requires_controller_approval`
  (line 817) — `ApplyExecutor.apply` with a non-approved decision returns
  `success=False` and writes nothing.

`ApplyExecutor` itself is a plain class with no `enabled` flag. It becomes
reachable only through `build_recovery_agent()` or `agent_run.py --recovery`
(`simulation/agent/recovery/recovery_assembly.py:40`). The default
`Agent(kernel)` path never constructs or invokes it.

Severity: LOW (informational). The claimed test name is wrong; the claimed
security property holds.

Existing tests: as above.
Missing test: a test that literally asserts `ApplyExecutor` has no
unconditional/self-activated apply path. Low value; not added.

### B) `patch.path not in patch.allowed_paths` exact-match / scope risk

**Classification: NOT REPRODUCED.**

There is no exact-membership check anywhere in the code
(`git grep 'not in .*allowed_paths'` finds nothing). Path scope is enforced
exclusively by `simulation/security/path_policy.py::PathPolicy.check_scope`,
which uses canonical scope **containment**, not string equality:

- `R2` (path_policy.py:21) — absolute and relative inputs are normalized with
  `Path.resolve(strict=False)` + `os.path.normcase` before comparison, so form
  mismatch cannot bypass the scope check.
- `R3` (path_policy.py:24) — any `..` component is rejected up front.
- `R4` (path_policy.py:28) — the canonical target must equal or descend from an
  allowed entry (`_within`, path_policy.py:220).
- `R5` (path_policy.py:31) — symlink/junction escapes are rejected because the
  resolved target leaves scope.

A scope entry may be a file (exact file allowed) or a directory (descendants
allowed). Empty scope, `None` scope and empty scope entries all fail closed
(path_policy.py:137-192).

Existing tests: `tests/security/path_security_test.py` (traversal, absolute,
symlink, junction, prefix-confusion, sibling out-of-scope, empty scope),
`tests/security/worker_read_scope_test.py` (read-side equivalents).
Missing test: none material.

Severity: LOW (informational).

### C) Controller's fragile dependency on Validator message text

**Classification: VERIFIED.**

`simulation/agent/controller/controller.py:25` decides approval with a string
equality test against a hard-coded literal:

```python
if validation_message != ("Patch validation passed."):
    return ControllerDecision(approved=False, ...)
```

The Controller's security decision therefore depends on a human-readable
message string rather than a typed/structured validation result. Any caller
that can produce the exact string "Patch validation passed." obtains an
approved decision regardless of how validation was reached, and any future
change to the validator message text silently breaks the approval gate.

The failure mode is partially fail-closed (an unknown message is rejected) but
the approved path is not anchored to structured state and is not resilient to
message drift.

Existing tests: `tests/worker_contract_test.py` lines 513-607 (approve with the
literal string, reject invalid string, reject unsupported action),
`tests/worker_action_pipeline_test.py` line 447 (asserts the exact literal is
passed through).
Missing test: malformed/typed-contract tests (covered in MISSION-007).

Severity: MEDIUM (contract fragility; approval gate not anchored to typed
state).
Fix: MISSION-007 replaces the string contract with a structured
`ValidationResult` (`valid: bool`), decided on `valid is True`, not on text.

---

## 2. Additional Findings From the Code Baseline

### D) `WorkerTask.allowed_actions` is carried but not enforced

**Classification: VERIFIED (enforcement gap) — FIXED in this mission.**

`simulation/agent/worker/worker_task.py:12` defines `allowed_actions` and
`WorkerExecutor` fills it with `("read", "inspect", "propose")`
(worker_executor.py:37). Before this mission, `WorkerAgent.run` never consulted
`task.allowed_actions`; it only checked the hard-coded `WorkerPolicy`
(worker_agent.py:55-77). A task constructed with `allowed_actions=("inspect",)`
still received full read/inspect/propose capability.

Minimal fail-closed fix applied in this mission:
`WorkerAgent.REQUIRED_ACTIONS = ("read", "inspect", "propose")` is now checked
against both `WorkerPolicy.allows(action)` and a new `_task_allows(task, action)`
guard. Semantics:

- `task.allowed_actions` empty (default) → unconstrained (policy governs;
  backward compatible with the existing test corpus).
- non-empty → every required action must be listed, otherwise the worker
  returns `WorkerResult(success=False, "Worker policy denied <action> action.")`.

Existing tests: `tests/security/worker_read_scope_test.py` (4 new tests).
Severity: MEDIUM → mitigated (default-deny when restricted).

### E) FileApplier TOCTOU between scope check and write

**Classification: OPEN (audit time) — HARDENED in MISSION-006.**

`simulation/agent/apply/file_applier.py` runs `PathPolicy.check_scope` on
`patch.path`, then later `Path(patch.path).write_text(...)`. Both the scope
check and the write resolve the path independently, leaving a small window in
which a symlink/junction at `patch.path` could be swapped after the check.
Severity: LOW in the current single-process context.

MISSION-006 hardening:
- `PathPolicy.resolve_target()` exposes the exact canonical form `check_scope`
  uses; `FileApplier` now reads and writes through that resolved target, so the
  write goes to the same verified path.
- After every write the target is read back; any mismatch with the approved
  `new_content` triggers a bounded restore of `old_content` and a FAIL
  ("Patch integrity check failed ... target restored").
- New deterministic tests in `tests/patch_integrity_test.py` (stale/concurrent
  modification, second stale patch on the same file, write-through in-scope
  symlink, corrupted-write detection + restore, approved-fingerprint == applied
  content, fingerprint-mismatch denial before write).

### F) Decision Trace is in-memory only

**Classification: OPEN (known, documented).**

`simulation/decision/decision_trace.py` keeps steps in memory; the durable
evidence is the hash-chained event log written by `WorkerEvidenceRecorder`.
This is a documented design decision (docs/PROJECT_STATE.md), not a regression.

### G) Idempotency — no duplicate suppression in the event store

**Classification: OPEN (documented).**

The event store is append-only with no dedup layer. Recovery-level duplicate
patch fingerprints are rejected by `BoundedRecoveryEngine` (test
`test_t09_duplicate_patch_is_not_blindly_reapplied`). A re-run of the same task
creates fresh events (append-only, no overwrite). Documented in MISSION-004.

### H) Hash verification failure output

**Classification: OPEN (informational).**

`simulation/security/hash_verifier.py:49` prints a Turkish diagnostic
("Hash bozuk:") to stdout on chain break. Informational only; no secret data.
`verify_chain.py` is the CLI entry for this.

---

## 3. Component-by-Component Baseline Summary

| Component | Behavior | Status |
|-----------|----------|--------|
| Worker read-side path scope | Scope enforced via PathPolicy before any read; out-of-scope reads produce denied evidence and no analyzer call | VERIFIED |
| Patch path scope | Enforced in PatchValidator and FileApplier | VERIFIED |
| Path traversal | `..` components rejected at both scope and patch level | VERIFIED |
| Absolute paths | Canonicalized via resolve + normcase; absolute-outside denied | VERIFIED |
| Symlink/junction behavior | Escapes rejected; in-scope symlinks accepted | VERIFIED (5 junction tests may skip) |
| allowed_paths | Empty/None/invalid entries fail closed | VERIFIED |
| allowed_actions | Now enforced when provided (this mission) | VERIFIED (new) |
| PatchProposal | Frozen dataclass; deterministic SHA-256 fingerprint over all fields | VERIFIED |
| old_content exact-match | Full-file exact match at validator and at write time | VERIFIED |
| Duplicate match | Analyzer requires exactly one occurrence of old_text | VERIFIED |
| Patch fingerprint/integrity | Controller approval binds fingerprint; ApplyAuthorization compares decision fingerprint to patch fingerprint | VERIFIED |
| ApplyExecutor | Requires approved decision with matching fingerprint; writes nothing otherwise | VERIFIED |
| Default-deny behavior | Default runtime is proposal-only; apply only via explicit assembly | VERIFIED |
| Validator | Checks path scope, file existence, file type, stale content, no-op change | VERIFIED |
| Controller | String-based approval (finding C) | VERIFIED — fixed in MISSION-007 |
| VerificationExecutor | Deterministic compile+tests; PASS/FAIL; evidence preserved | VERIFIED |
| BoundedRecoveryEngine | Hard cap 3 attempts; no recursion; duplicate fingerprint stops retries | VERIFIED |
| Decision Trace | Recorded per pipeline/recovery event via recorder | VERIFIED (in-memory) |
| Event Store | Append-only JSONL with SHA-256 hash chain | VERIFIED |
| hash/integrity chain | HashVerifier recomputes chain from GENESIS | VERIFIED |
| replay | Replay engine + reducer reconstruct state incl. worker_trace | VERIFIED |
| idempotency | No event-store dedup; recovery-level duplicate suppression | OPEN (documented) |

---

## 4. Security Invariants Asserted in This Audit

1. Apply success is never verification success (ApplyVerifyPipeline).
2. Unapproved or fingerprint-mismatched patches are never applied.
3. A stale patch (old_content mismatch) is never applied, even if it passed
   an earlier validation gate (FileApplier re-checks at write time).
4. Recovery is bounded; no caller-supplied value can raise the cap above 3.
5. Event evidence is hash-chained; any post-hoc mutation breaks verification.
6. No patch content or verification stdout/stderr is ever written to event
   payloads (only fingerprints and status/exit code).

---

## 5. Next Steps

- MISSION-006: harden the FileApplier write boundary (canonical path + read-back
  verification) and add deterministic integrity tests.
- MISSION-007: replace the Controller string contract with structured
  `ValidationResult` and add malformed-input fail-closed tests.
- MISSION-008: convert this threat model into an executable adversarial corpus
  (A01-A12).
- MISSION-009: synchronize MISSION_LOG / PROJECT_STATE / ROADMAP.
