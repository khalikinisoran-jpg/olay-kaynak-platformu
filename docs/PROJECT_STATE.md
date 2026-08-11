# PROJECT_STATE.md

# Event-Sourced AI Runtime

---

## Project Information

Project Name

Event-Sourced AI Runtime

Status

Active Development

Last Updated

2026-08-11

Active Branch

worker-action-pipeline

Branch HEAD

27effbf

---

# Vision

Build an enterprise-grade AI Runtime based on Event Sourcing.

Core Principles

- Event Driven
- Replayable
- Recoverable
- Tool Oriented
- Memory Aware
- Provider Agnostic
- Cryptographically Verifiable
- Enterprise Ready

Long-term direction: AI proposals must be validated, authorized, applied, verified and recorded as evidence before becoming trusted system mutations.

---

# Current Version

Latest release tag: v0.5.0

Codename

Sprint-17 — Executor Architecture & Memory Recall

Current development is post-v0.5.0 on the worker-action-pipeline branch (no new release tag yet).

---

# Current Sprint / Objective

Worker Action Pipeline & Bounded Verification Recovery & Decision Trace Evidence
& Security Kernel Hardening

Completed this sprint (MISSION-005..MISSION-008, branch worker-action-pipeline):

- MISSION-005 — Security baseline audit: `docs/SECURITY_BASELINE.md` with
  code+test evidence; three previously reported findings classified
  (A: NOT REPRODUCED as named but property verified by other tests;
  B: NOT REPRODUCED; C: VERIFIED and fixed in MISSION-007); `WorkerTask.allowed_actions`
  is now enforced (fail-closed when restricted).
- MISSION-006 — Patch integrity hardening: FileApplier writes through the
  canonical scope-verified path and verifies the write by read-back with
  bounded restore; new `tests/patch_integrity_test.py`.
- MISSION-007 — Controller decision hardening: typed `ValidationResult`
  contract; approval decided on `valid is True`, never on message text;
  malformed/missing/unknown input fails closed; new
  `tests/controller_decision_test.py`.
- MISSION-008 — Adversarial security test corpus V0.1
  (`tests/security/adversarial_corpus_test.py`, A01-A12 + sub-cases, 15 records,
  all PASS).

The apply/verify/recovery pipeline is NOT active by default. It becomes active
only when the runtime is explicitly assembled through build_recovery_agent()
(simulation/agent/recovery/recovery_assembly.py) or when agent_run.py is
started with --recovery. The default Agent(kernel) path (and the default
agent_run.py invocation) remains proposal-only: it never applies, verifies or
retries. Every pipeline/recovery decision is recorded as a
WorkerEvidenceRecorder event when the assembly is used.

---

# Current State Classification

This section is synchronized with the verified state on 2026-08-11.

Evidence hierarchy used:

1. Git history (commits)
2. Source code behavior
3. Automated test results (python -m pytest -q = 210 passed, 9 skipped)
4. Documentation (lowest priority; docs may be stale)

## VERIFIED

Code exists, is committed, and is covered by passing deterministic tests.

| Component | Evidence |
|-----------|----------|
| Core Event Sourcing (Event, State, Reducer, Kernel) | Committed; covered by root test suite |
| Persistence (Event Store, Replay, Snapshot Manager) | Committed; covered by root test suite |
| Persistence Recovery Engine (snapshot + replay + hash integrity) | Committed; covered by recovery_test.py |
| Hash Chain & Integrity Verification | Committed; covered by hash/verify chain tests |
| Planner, Loop Engine, Decision Trace | Committed; covered by planner/loop/decision trace tests |
| Tool Framework (BaseTool, Registry, Executor, Calculator) | Committed; covered by tool/registry tests |
| Memory (MemoryService, MemoryStored, store/recall executors) | Committed; covered by memory tests |
| Worker (WorkerAgent, WorkerExecutor, WorkerTask, WorkerPolicy, PatchGenerator, PatchProposal) | Committed; worker_contract_test.py, worker_read_scope_test.py, worker_runtime_test.py, worker_runtime_integration_test.py |
| Validator (PatchValidator) | Committed; worker_contract_test.py, path_security_test.py |
| Controller (Controller + ControllerDecision) | Committed; worker_contract_test.py, worker_action_pipeline_test.py |
| Apply (ApplyExecutor, ApplyAuthorization, FileApplier, ApplyResult) | Committed; worker_contract_test.py, path_security_test.py |
| Verification (VerificationExecutor, CommandRunner, VerificationResult, VerificationEvidence) | Committed; verification_executor_test.py |
| Worker Action Pipeline (WorkerActionPipeline, ApplyVerifyPipeline) | Committed; worker_action_pipeline_test.py, apply_verify_pipeline_test.py, worker_runtime_integration_test.py |
| Bounded Recovery (BoundedRecoveryEngine, RecoveryAttempt, RecoveryResult, RecoveryAssembly) | Committed (90400c9); recovery_engine_test.py (~2100 lines, attempt cap, duplicate-fingerprint prevention, fail-closed behavior, runtime assembly test) |
| Worker Decision Trace Evidence (WorkerEvidenceRecorder, worker_events factory, State.worker_trace, reducer replay) | Committed; tests/worker_evidence_test.py (13 tests: stage event ordering, payload safety, hash-chain integrity after pipeline run, replay reconstruction, recovery attempt/outcome events) |
| Path Security (PathPolicy: traversal, scope, symlink/junction policy) | Committed; path_security_test.py, worker_read_scope_test.py |
| Worker Task Action Scope (WorkerAgent enforces task.allowed_actions) | Committed (93a9d4b); worker_read_scope_test.py (4 tests) |
| Patch Integrity Boundary (FileApplier canonical-path write, read-back verify + restore, stale/concurrent denial, fingerprint==applied content) | Committed (f5d1fbc); patch_integrity_test.py (6 tests) |
| Controller Structured Decision Contract (ValidationResult; fail-closed on malformed/missing/unknown; message text is never the signal) | Committed (2249a04); controller_decision_test.py (13 tests) |
| Adversarial Security Corpus V0.1 (A01-A12 + sub-cases) | Committed (27effbf); adversarial_corpus_test.py (15 corpus records, all PASS, summary gate) |

## IMPLEMENTED BUT UNVERIFIED

Code exists but deterministic verification coverage is not complete.

- **LLM-driven patch analysis (LLMCodeAnalyzer)** — implementation exists, but every deterministic automated test uses FakeWorkerAnalyzer. Live LLM provider behavior is covered only by the opt-in `live_llm` integration test (`RUN_LIVE_LLM=1 python -m pytest -m live_llm tests/llm_provider_integration_test.py -q`), which passed on 2026-08-11 (2/2: in-memory proposal and Worker proposal-only chain).
- **Recovery through the shipped entry point** — agent_run.py now exposes an opt-in `--recovery` mode that wires build_recovery_agent (apply + verify + bounded recovery). The assembly itself is covered by recovery_engine_test.py (test_f2) and worker_evidence_test.py, but an automated end-to-end CLI interaction (`python agent_run.py --recovery`) has no automated test; the default invocation stays proposal-only and unverified as a mutation path.

## NOT IMPLEMENTED

Documented in ROADMAP.md but no implementation exists.

- Structured worker AnalysisResult contract (diagnosis, evidence, confidence, risk, explanation) — current analyzer returns only diagnosis/old_text/new_text
- Risk classification engine (LOW / MEDIUM / HIGH / CRITICAL)
- Human-in-the-loop approval boundary
- Secret scanning and supply-chain protection
- Runtime benchmarks (event append / replay / snapshot / hash / recovery latency)
- Multi-agent / multi-worker concurrency testing
- Full recovery scenario coverage (process restart, snapshot recovery, replay + hash-chain integrity after recovery)
- External / compliance / commercial validation
- Persistent decision trace (DecisionTrace remains in-memory; the hash-chained event log is the durable evidence)

## UNKNOWN

Cannot be classified from available evidence.

- Live LLM end-to-end behavior and JSON contract compliance with a real provider (proposal-only level verified via gated test; full pipeline including apply/verification/recovery still untested live)
- Security behavior on environments where symlink creation is unavailable (7 symlink-dependent tests skip when the OS denies symlink creation; junction tests pass on this Windows environment)
- Production/deployment behavior (no production configuration exists)

---

# Completed Features

## Core Runtime

- Event
- State
- Reducer
- Kernel

## Persistence

- Event Store
- Replay Engine
- Snapshot Manager
- Recovery Engine (snapshot + replay + hash-integrity reconstruction)

## Security

- Hash Chain
- Integrity Verification (Verify Chain)
- Path Policy (scope, traversal, symlink/junction containment)

## Runtime

- Planner
- Loop Engine
- Decision Trace
- Executor Registry & Strategy Dispatcher

## Tool Framework

- BaseTool
- Tool Registry
- Tool Executor
- Calculator Tool

## Memory

- MemoryService
- MemoryStored Event
- MemoryEvents Factory
- Automatic Memory Store
- Memory Recall Executor

## Worker Action Pipeline

- Worker Agent (proposal-only by default)
- LLM-driven patch analysis
- Patch Proposal + deterministic fingerprint
- Patch Validator
- Controller authorization
- Apply Executor + File Applier (fingerprint-matched approval)
- Verification Executor (compile + pytest, PASS/FAIL, evidence preserved)
- Worker Action Pipeline (per-proposal gates, fail-closed)
- Bounded Verification Recovery (max 3 attempts, append-only attempt history)
- Worker Decision Trace Evidence (WorkerEvidenceRecorder: 13 hash-chained lifecycle events + DecisionTrace steps; secret-safe payloads, patch content stored only as fingerprint)
- Opt-in `--recovery` mode in agent_run.py (apply + verification + bounded recovery wired to the shipped entry point; default stays proposal-only)
- OpenRouter provider hardening (connect/read timeout, fail-closed ProviderError, secret-safe logging, no debug prints)
- Gated real-LLM integration test (`live_llm` marker; opt-in only, proposal-only, no file mutation)
- Security Baseline Audit (docs/SECURITY_BASELINE.md: severity, evidence, existing/missing tests)
- Worker Task Action Scope enforcement (task.allowed_actions fail-closed when restricted)
- Patch Integrity Boundary hardening (canonical-path write + read-back verification + bounded restore; stale/concurrent denial; approved-fingerprint == applied content)
- Controller Structured Decision Contract (ValidationResult; typed fail-closed approval)
- Adversarial Security Test Corpus V0.1 (A01-A12, executable, summary-gated)

---

# Verified Baseline

Test suite: 210 passed, 9 skipped (python -m pytest -q, 2026-08-11). The 9 skipped tests are: 2 opt-in `live_llm` integration tests that never run in the normal suite (no API cost, no provider call), and 7 symlink-dependent tests (5 baseline path-security/read-scope, 1 patch-integrity, 1 adversarial corpus) skipped where the OS denies symlink creation (Windows requires elevation or Developer Mode). Junction-based escape tests use `mklink /J` and pass on this environment.

Live LLM (opt-in): `RUN_LIVE_LLM=1 python -m pytest -m live_llm tests/llm_provider_integration_test.py -q` = 2 passed (2026-08-11): real provider produces an in-memory proposal; real Worker + real LLM chain produces a proposal without mutating the file.

git diff --check: clean.

Working tree: clean on worker-action-pipeline @ 27effbf.

---

# Next Milestone

Unreleased. Candidate areas (see ROADMAP.md):

- Structured worker analysis contract
- Risk classification
- Human approval boundary
- Secret scanning
- Persistent decision trace / durable trace reconstruction
- Recovery enabled in the default (flag-less) runtime — requires an explicit product decision (apply stays non-default by design)
- Multi-agent / concurrent event-write testing
- Benchmark measurements (event append / replay / hash)

---

# Notes

This document is synchronized with actual code, git history and test results.

Stale documentation must not be trusted over code and git history.
