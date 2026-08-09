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

Current verified baseline:

- Full test suite: 28 passed
- Working tree verified clean
- Worker contract tests isolated from the live LLM

---

# Phase 1 - Verification

## 1. VerificationExecutor

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
- Keep the first implementation deterministic
- Do not depend on an LLM for verification

---

# Phase 2 - Verification Evidence

## 2. Structured VerificationResult

A verification failure must produce useful evidence.

Potential structure:

VerificationResult
- success
- exit_code
- stdout
- stderr
- test_name
- failure_reason
- evidence

The result must be sufficient for a later Worker
re-analysis without relying on hidden state.

---

# Phase 3 - Closed-Loop Recovery

## 3. Controlled Retry

If verification fails:

Verification Failure
-> Evidence
-> Worker Re-analysis
-> New Proposal
-> Validation
-> Controller
-> Apply
-> Verification

Requirements:

- Limit retry count
- Preserve every attempt
- Never silently overwrite previous proposals
- Record failure evidence
- Prevent retry/probing abuse
- Never allow unlimited self-modification

Initial target:

max_attempts = 3

---

# Phase 4 - Structured LLM Result

## 4. AnalysisResult

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

---

# Phase 5 - Event & Decision Trace

## 5. Worker Event Lifecycle

Worker operations should become auditable events.

Potential event sequence:

WorkerTaskCreated
-> WorkerInspectionCompleted
-> PatchProposed
-> PatchValidated
-> PatchApproved
-> PatchApplied
-> VerificationCompleted

The purpose is to answer:

"Why did the Worker make this change?"

The answer should be reconstructable from recorded evidence.

---

## 6. Structured Decision Trace

Potential decision chain:

Task
-> Evidence
-> LLM Analysis
-> Patch
-> Validation
-> Authorization
-> Application
-> Verification

The trace should support reproducibility and auditability.

---

# Phase 6 - Security Enforcement

## 7. Security Boundaries

Security requirements must be enforced by code and tests,
not only documented.

### Path Security

- allowed_paths
- path traversal prevention
- absolute path policy
- symlink policy

### Action Security

Separate:

- read
- inspect
- propose
- modify
- execute

### Approval Boundary

Worker:

"I want to perform this action."

Controller:

"I authorize this action."

ApplyExecutor:

"The applied fingerprint exactly matches the approved
fingerprint."

---

# Phase 7 - Risk & Policy Engine

## 8. Risk Classification

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

# Phase 8 - Human Approval Boundary

## 9. Human-in-the-Loop

Define explicit operations that require human approval.

Potential examples:

- High-risk file modifications
- Security-sensitive changes
- Production changes
- Configuration changes
- Irreversible operations

Human approval should be represented as an explicit
authorization event.

---

# Phase 9 - Reliability, Scale & Concurrency

## 10. Runtime Benchmarks

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

## 11. Multi-Agent / Multi-Worker Testing

Test:

- Concurrent event writes
- Concurrent workers
- Snapshot races
- Replay consistency
- Hash-chain integrity
- Duplicate operations
- Retry races

The goal is to identify race conditions before production use.

---

# Phase 10 - Secret & Supply-Chain Protection

## 12. Secret Scanning

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

---

# Phase 11 - Full Agent Loop

## 13. Integrated Agent Runtime

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

The retry loop must remain bounded and auditable.

---

# Phase 12 - Compliance & Commercial Validation

## 14. External Validation

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

---

# Engineering Rule

> Claim -> Test -> Measure -> Fix -> Verify

No architectural assumption should become a permanent system
requirement without evidence when that assumption can be tested.

AI-generated conclusions are hypotheses until supported by
observable evidence or deterministic validation.

---

# Current Next Step

The immediate engineering target is:

## VerificationExecutor

Worker
-> Validator
-> Controller
-> Apply
-> Verification
-> PASS / FAIL

First implementation goal:

1. Create VerificationResult
2. Create VerificationExecutor
3. Run py_compile
4. Run the relevant pytest target
5. Capture verification evidence
6. Add deterministic tests
7. Integrate with the existing Apply pipeline
8. Run the complete test suite
9. Commit only after verification passes