# Project Roadmap

## Current Baseline

The current system has:

- Event sourcing
- Event replay
- Snapshot support
- Hash/integrity mechanisms
- Worker agent
- LLM-driven code analysis
- Patch proposal generation
- Patch validation
- Controller authorization
- Controlled file application
- Worker contract tests
- Isolated worker analyzer tests
- Project vision and roadmap documentation

Current verified baseline:

- Full test suite: 210 passed, 9 skipped
- Working tree verified clean
- Worker contract tests isolated from the live LLM
- Main branch synchronized with origin
- Worker Action Pipeline + Bounded Recovery + Decision Trace Evidence
  (MISSION-003/004) on branch worker-action-pipeline
- Security Kernel hardening (MISSION-005..MISSION-008): security baseline
  audit (docs/SECURITY_BASELINE.md), worker task action scope enforcement,
  patch integrity boundary (canonical write + read-back + restore), typed
  Controller validation contract (ValidationResult, fail-closed), adversarial
  security corpus V0.1 (A01-A12, summary-gated)

---

# Phase 1 - Verification Contract

## 1. VerificationResult

First establish a deterministic result contract for verification.

Potential structure:

VerificationResult
- success
- exit_code
- stdout
- stderr
- command
- test_name
- failure_reason
- evidence

Rules:

- Verification must produce an explicit PASS or FAIL result.
- Application success must never be treated as verification success.
- Verification evidence must be preserved.
- The result must be usable by later recovery logic.
- The first implementation must not depend on an LLM.

---

# Phase 2 - Verification Execution

## 2. VerificationExecutor

Goal:

Verify that an applied patch actually produces the expected
runtime behavior.

Pipeline:

Worker
-> Validator
-> Controller
-> Apply
-> Verification

Initial implementation:

Apply
-> VerificationExecutor
-> py_compile
-> relevant pytest
-> VerificationResult

Requirements:

- Execute relevant verification tests
- Capture stdout/stderr
- Capture exit status
- Record verification evidence
- Distinguish PASS from FAIL
- Never treat application success as verification success
- Keep execution deterministic
- Prevent verification from modifying unrelated project state

---

# Phase 3 - Verification Evidence

## 3. Failure Evidence

A failed verification must produce structured evidence.

Potential structure:

Verification Failure
- command
- exit_code
- stdout
- stderr
- failed_test
- failure_reason
- evidence

The evidence must be sufficient for a later Worker
re-analysis without relying on hidden state.

Rules:

- Preserve every verification attempt
- Never silently overwrite previous evidence
- Make failures reproducible where possible
- Separate verification evidence from LLM interpretation

---

# Phase 4 - Controlled Recovery

## 4. Closed-Loop Retry

If verification fails:

Verification Failure
-> Evidence
-> Worker Re-analysis
-> New Proposal
-> Validation
-> Controller
-> Apply
-> Verification

Initial target:

max_attempts = 3

Requirements:

- Limit retry count
- Preserve every attempt
- Never silently overwrite previous proposals
- Record failure evidence
- Prevent retry/probing abuse
- Never allow unlimited self-modification
- A failed retry must terminate safely

Target behavior:

PASS
-> Accept

FAIL
-> Re-analyze if attempts remain

FAIL + attempts exhausted
-> Stop
-> Preserve evidence
-> Require external intervention

---

# Phase 5 - Worker Intelligence Contract

## 5. Structured LLM Result

The Worker analysis should evolve from a minimal patch response
into a structured analysis contract.

Potential structure:

AnalysisResult
- diagnosis
- evidence
- confidence
- old_text
- new_text
- risk
- explanation

Important rule:

LLM confidence is a signal, not a security decision.

LLM claims must be supported by evidence and validated by
deterministic system controls.

The system must not assume that an LLM diagnosis is correct
merely because the model produced it.

---

# Phase 6 - Security Enforcement

## 6. Security Boundaries

Security requirements must be enforced by code and tests,
not only documented.

### Path Security

- allowed_paths
- path traversal prevention
- absolute path policy
- symlink policy
- path normalization

### Action Security

Separate:

- read
- inspect
- propose
- modify
- execute

### Patch Security

Verify:

- old_text exists
- old_text occurs exactly once when required
- new_content is actually different
- target path is allowed
- patch fingerprint is valid
- approved fingerprint matches the applied fingerprint

### Approval Boundary

Worker:

"I want to perform this action."

Controller:

"I authorize this action."

ApplyExecutor:

"The applied fingerprint exactly matches the approved
fingerprint."

---

# Phase 7 - Secret & Supply-Chain Protection

## 7. Secret Scanning

Introduce system-enforced protection for:

- API keys
- Tokens
- Credentials
- Environment secrets
- Accidental secret commits

Desired direction:

Secret Scanning
+
.gitignore
+
Pre-commit Checks
+
CI Validation

Security should not depend on human memory.

The system should detect secrets before they become part of
the repository history whenever technically possible.

---

# Phase 8 - Event & Decision Trace

## 8. Worker Event Lifecycle

Worker operations should become auditable events.

Potential event sequence:

WorkerTaskCreated
-> WorkerInspectionCompleted
-> PatchProposed
-> PatchValidated
-> PatchApproved
-> PatchApplied
-> VerificationCompleted

Recovery should also become observable:

VerificationFailed
-> RetryRequested
-> WorkerReanalysisStarted
-> NewPatchProposed

The purpose is to answer:

"Why did the Worker make this change?"

The answer should be reconstructable from recorded evidence.

---

## 9. Structured Decision Trace

Potential decision chain:

Task
-> Evidence
-> LLM Analysis
-> Patch
-> Validation
-> Authorization
-> Application
-> Verification
-> Recovery if required

The trace should support:

- reproducibility
- auditability
- debugging
- recovery analysis

---

# Phase 9 - Risk & Policy Engine

## 10. Risk Classification

Introduce explicit risk levels:

- LOW
- MEDIUM
- HIGH
- CRITICAL

Risk should influence:

- Required validation
- Required authorization
- Whether automatic application is allowed
- Whether human approval is required
- Verification depth
- Retry permissions

Risk should not depend exclusively on an LLM-provided
risk value.

Potential system signals:

- path
- action
- file type
- scope
- environment
- change size
- security sensitivity

---

# Phase 10 - Human Approval Boundary

## 11. Human-in-the-Loop

Define explicit operations that require human approval.

Potential examples:

- High-risk file modifications
- Security-sensitive changes
- Production changes
- Configuration changes
- Irreversible operations

Human approval should be represented as an explicit
authorization event.

Potential flow:

Worker
-> Validator
-> Risk Engine
-> Human Approval
-> Controller
-> Apply
-> Verification

---

# Phase 11 - Reliability, Scale & Concurrency

## 12. Runtime Benchmarks

Measure:

- Event append latency
- Replay latency
- Snapshot latency
- Hash calculation cost
- Recovery time
- Memory usage

Benchmark targets:

- 1,000 events
- 10,000 events
- 100,000 events
- Larger datasets as required

Do not assume a bottleneck exists.
Measure first.

---

## 13. Multi-Agent / Multi-Worker Testing

Test:

- Concurrent event writes
- Concurrent workers
- Snapshot races
- Replay consistency
- Hash-chain integrity
- Duplicate operations
- Retry races
- Verification races

The goal is to identify race conditions before production use.

---

# Phase 12 - Full Agent Loop

## 14. Integrated Agent Runtime

Target architecture:

USER TASK
-> CONTROLLER
-> WORKER
-> MEMORY / LLM
-> ANALYSIS
-> PATCH PROPOSAL
-> VALIDATOR
-> CONTROLLER
-> APPLY
-> VERIFICATION

Verification result:

PASS
-> ACCEPT

FAIL
-> FAILURE EVIDENCE
-> RE-ANALYZE
-> NEW PROPOSAL
-> VALIDATION
-> AUTHORIZATION
-> APPLY
-> VERIFICATION

The retry loop must remain:

- bounded
- auditable
- policy-controlled
- recoverable

---

# Phase 13 - Recovery & Replay Integrity

## 15. Full Recovery Testing

Verify that the system can reconstruct meaningful state after:

- verification failure
- interrupted application
- retry
- process restart
- snapshot recovery
- replay

Validate:

- event ordering
- snapshot consistency
- hash-chain integrity
- decision trace continuity
- recovery determinism

---

# Phase 14 - Compliance & Commercial Validation

## 16. External Validation

After the technical foundation is sufficiently mature:

- Research applicable regulations
- Verify compliance requirements against official sources
- Identify target customers
- Define commercial use cases
- Evaluate competing products
- Define product differentiation
- Validate the market hypothesis

Compliance claims must be verified against authoritative
sources before being used as product claims.

Commercial claims must be separated from technical evidence.

---

# Engineering Rules

## Rule 1 - Evidence First

> Claim -> Test -> Measure -> Fix -> Verify

No architectural assumption should become a permanent system
requirement without evidence when that assumption can be tested.

---

## Rule 2 - AI Is Not Authority

AI-generated conclusions are hypotheses until supported by:

- observable evidence
- deterministic validation
- policy checks
- authorization
- verification

---

## Rule 3 - Application Is Not Verification

A successful file write does not mean the change is correct.

The system must distinguish:

Apply Success
from
Verification Success

---

## Rule 4 - No Unlimited Self-Modification

A Worker must never be allowed to repeatedly modify the system
without bounded attempts and explicit policy.

---

## Rule 5 - Security Must Be Executable

Security requirements must exist as:

- code
- contracts
- tests
- enforcement boundaries

Documentation alone is insufficient.

---

## Rule 6 - Preserve Evidence

Every significant AI-driven action should leave enough evidence
to reconstruct what happened and why.

---

# Current Next Step

The immediate engineering target is:

## VerificationResult

Then:

## VerificationExecutor

Target pipeline:

Worker
-> Validator
-> Controller
-> Apply
-> VerificationExecutor
-> VerificationResult
-> PASS / FAIL

First implementation sequence:

1. Define VerificationResult
2. Write deterministic contract tests
3. Create VerificationExecutor
4. Implement py_compile verification
5. Implement relevant pytest verification
6. Capture stdout/stderr and exit status
7. Add failure evidence
8. Integrate with the existing Apply pipeline
9. Run the complete test suite
10. Commit only after verification passes

After that:

Closed-loop recovery.