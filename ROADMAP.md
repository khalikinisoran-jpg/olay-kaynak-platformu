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

# Phase 1 — Verification

## 1. VerificationExecutor

Goal:

Verify that an applied patch actually produces the expected
runtime behavior.

Pipeline:

Worker
→ Validator
→ Controller
→ Apply
→ Verification

Requirements:

- Execute relevant verification tests
- Capture stdout/stderr
- Capture exit status
- Record verification evidence
- Distinguish PASS from FAIL
- Never treat application success as verification success

---

# Phase 2 — Closed-Loop Recovery

## 2. Controlled Retry

If verification fails:

Verification Failure
→ Evidence
→ Worker Re-analysis
→ New Proposal
→ Validation
→ Controller
→ Apply
→ Verification

Requirements:

- Limit retry count
- Preserve every attempt
- Never silently overwrite previous proposals
- Record failure evidence
- Prevent retry/probing abuse

---

# Phase 3 — Reliability & Scale

## 3. Runtime Benchmarks

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

# Phase 4 — Concurrency

## 4. Multi-Agent / Multi-Worker Testing

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

# Phase 5 — Security Enforcement

## 5. Security Boundaries

Verify that security policies are enforced by code.

Areas:

- Path escape prevention
- Allowed-path enforcement
- Action restrictions
- Privilege boundaries
- Patch scope validation
- Controller approval requirements
- Apply authorization
- Retry/probing protection
- Integrity boundary protection

Security requirements must be executable and testable,
not merely documented.

---

# Phase 6 — Secret & Supply-Chain Protection

## 6. Secret Scanning

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

# Phase 7 — Decision Trace

## 7. Structured Decision Evidence

Every significant AI-driven action should be traceable.

Potential structure:

Decision
→ Input
→ Context
→ Model
→ Proposal
→ Evidence
→ Validation
→ Authorization
→ Action
→ Result

The goal is reproducibility and auditability.

---

# Phase 8 — Risk Engine

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

---

# Phase 9 — Human Approval Boundary

## 9. Human-in-the-Loop

Define explicit actions that require human approval.

Potential examples:

- High-risk file modifications
- Security-sensitive changes
- Production changes
- Configuration changes
- Irreversible operations

Human approval should be represented as an explicit
authorization event rather than an informal external decision.

---

# Phase 10 — Compliance & Commercial Research

## 10. External Validation

After the technical foundation is sufficiently mature:

- Research applicable regulations
- Verify compliance requirements against official sources
- Identify target customers
- Define commercial use cases
- Evaluate competing products
- Define product differentiation
- Validate the market hypothesis

Compliance claims must be verified against authoritative sources.

---

# Engineering Rule

> Claim → Test → Measure → Fix → Verify

No architectural assumption should become a permanent system
requirement without evidence when that assumption can be tested.

---

# Current Next Step

The immediate engineering target is:

## VerificationExecutor

Worker
→ Validator
→ Controller
→ Apply
→ Verification
→ PASS / FAIL