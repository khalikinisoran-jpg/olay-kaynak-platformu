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

18a1f6c

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

Worker Action Pipeline & Bounded Verification Recovery

Current mission (MISSION-003): OpenRouter provider hardening (request timeout, fail-closed error handling, secret-safe logging, debug print removal) and a gated real-LLM proposal-only integration test (`live_llm` marker, opt-in via `RUN_LIVE_LLM=1`).

Current pipeline (implemented and committed):

Worker
→ Validator
→ Controller
→ Apply
→ Verification
→ Bounded Recovery (max 3 attempts)

Recovery is NOT active by default. It becomes active only when the runtime is explicitly assembled through build_recovery_agent() (simulation/agent/recovery/recovery_assembly.py). The default Agent(kernel) path (and agent_run.py) remains proposal-only: it never applies, verifies or retries.

---

# Current State Classification

This section is synchronized with the verified state on 2026-08-11.

Evidence hierarchy used:

1. Git history (commits)
2. Source code behavior
3. Automated test results (python -m pytest -q = 159 passed, 7 skipped)
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
| Path Security (PathPolicy: traversal, scope, symlink/junction policy) | Committed; path_security_test.py, worker_read_scope_test.py |

## IMPLEMENTED BUT UNVERIFIED

Code exists but deterministic verification coverage is not complete.

- **LLM-driven patch analysis (LLMCodeAnalyzer)** — implementation exists, but every deterministic automated test uses FakeWorkerAnalyzer. Live LLM provider behavior is covered only by the opt-in `live_llm` integration test (`RUN_LIVE_LLM=1 python -m pytest -m live_llm tests/llm_provider_integration_test.py -q`), which passed on 2026-08-11 (2/2: in-memory proposal and Worker proposal-only chain).
- **Recovery in the shipped runnable entry point** — the recovery assembly is tested in isolation (test_f2), but agent_run.py uses the default Agent(kernel) and does not enable the pipeline/recovery. End-to-end operation through the shipped entry point is not verified.
- **Decision trace for the worker pipeline** — DecisionTrace exists and is tested for the LLM loop, but it is not integrated with the worker action pipeline (no trace record for validation/apply/verification/recovery steps).

## NOT IMPLEMENTED

Documented in ROADMAP.md but no implementation exists.

- Worker event lifecycle persisted to the event store (WorkerTaskCreated, PatchProposed, PatchValidated, PatchApproved, PatchApplied, VerificationCompleted, VerificationFailed, RetryRequested...)
- Structured worker AnalysisResult contract (diagnosis, evidence, confidence, risk, explanation) — current analyzer returns only diagnosis/old_text/new_text
- Risk classification engine (LOW / MEDIUM / HIGH / CRITICAL)
- Human-in-the-loop approval boundary
- Secret scanning and supply-chain protection
- Runtime benchmarks (event append / replay / snapshot / hash / recovery latency)
- Multi-agent / multi-worker concurrency testing
- Full recovery scenario coverage (process restart, snapshot recovery, replay + hash-chain integrity after recovery)
- External / compliance / commercial validation

## UNKNOWN

Cannot be classified from available evidence.

- Live LLM end-to-end behavior and JSON contract compliance with a real provider (proposal-only level verified via gated test; full pipeline including apply/verification/recovery still untested live)
- Security behavior on environments where symlink/junction tests are skipped (5 junction-dependent tests skip when junction creation is unavailable)
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
- OpenRouter provider hardening (connect/read timeout, fail-closed ProviderError, secret-safe logging, no debug prints)
- Gated real-LLM integration test (`live_llm` marker; opt-in only, proposal-only, no file mutation)

---

# Verified Baseline

Test suite: 159 passed, 7 skipped (python -m pytest -q, 2026-08-11). The 7 skipped tests are: 5 junction-dependent path-security tests and 2 opt-in `live_llm` integration tests that never run in the normal suite (no API cost, no provider call).

Live LLM (opt-in): `RUN_LIVE_LLM=1 python -m pytest -m live_llm tests/llm_provider_integration_test.py -q` = 2 passed (2026-08-11): real provider produces an in-memory proposal; real Worker + real LLM chain produces a proposal without mutating the file.

git diff --check: clean.

Working tree: clean on worker-action-pipeline @ 18a1f6c.

---

# Next Milestone

Unreleased. Candidate areas (see ROADMAP.md):

- Worker event lifecycle as auditable events
- Structured worker analysis contract
- Risk classification
- Human approval boundary
- Secret scanning
- Recovery wired into the shipped runtime entry point

---

# Notes

This document is synchronized with actual code, git history and test results.

Stale documentation must not be trusted over code and git history.
