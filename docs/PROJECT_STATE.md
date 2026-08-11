# PROJECT_STATE.md

# Event-Sourced AI Runtime

Canonical project state. Source of truth for what actually exists.
Evidence hierarchy: Git history > source code behavior > automated test
results > documentation.

---

## Project Information

| Field | Value | Classification |
|-------|-------|----------------|
| Project Name | Event-Sourced AI Runtime | VERIFIED (docs) |
| Status | Active Development | VERIFIED (git activity) |
| Last Updated | 2026-08-12 | VERIFIED |
| Active Branch | `worker-action-pipeline` | VERIFIED (`git branch`) |
| Branch HEAD | `96ed72d` (Integrate risk-aware worker action pipeline) | VERIFIED (`git rev-parse HEAD`) |
| Remote | `origin` = https://github.com/khalikinisoran-jpg/olay-kaynak-platformu.git | VERIFIED (`git remote -v`) |
| Branch relationship | `worker-action-pipeline` is 14 commits ahead of `main`; `main` has 0 commits not in `worker-action-pipeline` | VERIFIED (`git log main..HEAD`, `git log HEAD..main`) |
| Latest release tag | v0.5.0 (2026-08-07, "Memory Recall Runtime") | VERIFIED (`git tag`) |
| Tags | v0.1.0-alpha, v0.3.0, v0.4.0, v0.5.0 | VERIFIED |
| Python | 3.12 (pyc artifacts indicate cpython-312); pytest 9.1.1 in `.venv` | VERIFIED (`.venv\Scripts\python.exe -m pytest --version`) |

---

# Purpose

Build an event-sourced AI runtime in which every meaningful AI action
becomes an immutable, hash-chained event, so that AI-driven decisions can
be replayed, recovered, verified, audited and constrained by deterministic
system controls.

Product claim (not yet externally validated): "trustworthy AI through
Event Sourcing, Replay, and Verification." See docs/PRODUCT_POSITIONING.md.

---

# Current Product Definition

What is actually implemented and verifiable today:

- A CLI runtime (`agent_run.py`) that routes user input through a Planner
  to a StrategyDispatcher with five executors: `calculator`, `memory_store`,
  `memory_recall`, `llm`, `worker`.
- A proposal-only default path: a `worker:` prefixed prompt makes the
  Worker read in-scope files and produce patch proposals, but the default
  runtime never applies them (`simulation/agent/agent.py:46`, tests
  `tests/worker_runtime_test.py::test_default_agent_runtime_is_proposal_only_no_apply_no_verify`).
- An opt-in mutation path: `python agent_run.py --recovery` wires
  `build_recovery_agent()` which enables apply + verification + bounded
  recovery for in-scope files (`agent_run.py:52`, `simulation/agent/recovery/recovery_assembly.py`).
- A real-LLM code analyzer (OpenRouter, DeepSeek) behind a hardened
  provider layer; only proposal generation, never file mutation
  (MISSION-003, gated `live_llm` tests).
- A risk/verification pipeline (RiskEngine/RiskPolicy/RiskLevel) that is
  deterministic, tested (MISSION-011: 83 tests) and correctly integrated as
  an explicit opt-in gate at the pipeline and assembly level; it is NOT
  active in the default runtime (see Known Limitations).

---

# Current Architecture

Described in detail in docs/ARCHITECTURE.md. Summary of what exists in code:

1. Core event sourcing: `Event`, `State`, `Reducer`, `Kernel`
   (simulation/core/).
2. Persistence: `EventStore` (append-only JSONL + SHA-256 hash chain),
   `SnapshotStore`, `SnapshotManager`, `RecoveryEngine` (snapshot + replay
   + hash-integrity) (simulation/persistence/, simulation/recovery/,
   simulation/replay/, simulation/security/hash_chain.py).
3. Runtime orchestration: `Planner`, `LoopEngine`, `DecisionTrace`,
   `StrategyDispatcher`, `ExecutorRegistry` + executors (calculator,
   memory_store, memory_recall, llm, worker).
4. Memory: `MemoryService`, `MemoryEvents`, `MemoryStored` event,
   automatic store / recall executors.
5. Tools: `BaseTool`, `Registry`, `ToolExecutor`, `Calculator`.
6. Worker action pipeline (opt-in): `WorkerAgent` -> `PatchValidator` ->
   `Controller` -> `ApplyExecutor`/`FileApplier` -> `VerificationExecutor`
   -> optional `BoundedRecoveryEngine`, recorded by `WorkerEvidenceRecorder`
   (simulation/agent/pipeline/, simulation/agent/recovery/,
   simulation/agent/evidence/).
7. Risk engine (VERIFIED, MISSION-011): `RiskEngine`, `RiskPolicy`,
   `RiskLevel` (simulation/security/risk_*.py). Deterministic system-derived
   classification; advisory LLM risk can only raise; policy maps UNKNOWN->
   DENY, HIGH/CRITICAL->human approval, LOW/MEDIUM->auto. Integrated as an
   explicit opt-in gate in `WorkerActionPipeline` and `build_recovery_agent`.
8. Security: `PathPolicy` (canonical containment, traversal/symlink/junction
   rejection), `HashVerifier`, fail-closed validation contracts.

---

# Security Boundary

Detailed in docs/SECURITY_MODEL.md. Current boundary (all VERIFIED except
where noted):

- Path scope enforced by `PathPolicy.check_scope` (canonical resolve +
  normcase + containment) and re-checked at write time in `FileApplier`
  through `PathPolicy.resolve_target`.
- Patch validation requires exact full-file `old_content` match, in-scope
  target, `modify` action only, non-empty change.
- Apply requires a `ControllerDecision` with `approved is True` and a
  fingerprint that exactly matches the patch (ApplyAuthorization).
- Post-write read-back: written bytes are compared to approved
  `new_content`; mismatch triggers bounded restore + FAIL.
- Verification is deterministic (compileall + pytest via non-shell arg
  list); apply success is never verification success.
- Retry is bounded (hard cap 3; no recursion; duplicate fingerprints stop).
- Default runtime is proposal-only; apply only via explicit assembly.
- Risk gate is an explicit opt-in (requires both `risk_engine` and
  `risk_policy` on `WorkerActionPipeline` or `build_recovery_agent`). When
  active: RiskEngine -> RiskPolicy -> Controller -> ApplyVerifyPipeline,
  UNKNOWN/DENY stops before apply, HIGH/CRITICAL require human approval
  (blocked until MISSION-012 provides an approval store). **VERIFIED** —
  tests/risk_*.py (MISSION-011).

---

# Verification Model

- Deterministic verification layers: `PatchValidator` (scope/staleness),
  `Controller` (typed `ValidationResult`, `valid is True` only), `ApplyVerifyPipeline`
  (apply must pass before verification runs), `VerificationExecutor`
  (`python -m compileall -q <paths>` then `python -m pytest -q <targets>`,
  PASS/FAIL with preserved stdout/stderr/exit code/evidence).
- Verification depth switch (`compile` vs `compile+tests`) added in MISSION-011
  (`apply_verify_pipeline.py:31`). Both paths are now tested (MISSION-011):
  `verification_depth="compile"` calls `verify_python_compile` only;
  default/`compile+tests` calls `verify`. The policy currently selects
  `compile+tests` for every non-deny level.
- Live LLM behavior is only covered by opt-in gated tests
  (`RUN_LIVE_LLM=1 python -m pytest -m live_llm tests/llm_provider_integration_test.py -q`).

---

# Recovery Model

Two distinct recovery mechanisms exist:

1. **Persistence recovery** (`simulation/recovery/recovery_engine.py`):
   verifies hash chain, loads snapshot if present, replays remaining
   events. Wired into `Kernel.__init__` (every Kernel start).
2. **Bounded verification recovery** (`simulation/agent/recovery/bounded_recovery_engine.py`):
   retries a verification FAIL up to a hard cap of 3 attempts with
   duplicate-fingerprint suppression and append-only attempt history.
   Active only when the agent is assembled via `build_recovery_agent()`
   or `agent_run.py --recovery`.

Recovery is NOT active by default in the shipped runtime
(`agent_run.py` uses proposal-only `Agent(kernel)` unless `--recovery`).

---

# Evidence / Audit Model

- Every `kernel.dispatch()` writes a normal Event into the append-only
  EventStore with `previous_hash`/`current_hash` (SHA-256 chain);
  `HashVerifier.verify` recomputes from GENESIS.
- `WorkerEvidenceRecorder` (MISSION-004) records 13 worker lifecycle event
  types plus DecisionTrace steps. Payloads are secret-safe: only patch
  fingerprints (SHA-256) and status/exit-code/failure-reason, never
  old/new content, stdout/stderr, or API keys.
- DecisionTrace is in-memory only; the hash-chained event log is the
  durable evidence (documented design decision, ADR-001 / MISSION-004).

---

# Test State

Authoritative run on 2026-08-12 (MISSION-011 close-out):

```
.venv\Scripts\python.exe -m pytest -q
334 passed, 9 skipped in ~5s
```

- 22 collected test modules (20 under tests/, including tests/security/
  sub-package, plus root recovery_test.py).
- 9 skipped: 2 opt-in `live_llm` integration tests (never run in the
  normal suite; no API cost) + 7 symlink-dependent tests that skip where
  the OS denies symlink creation (junction variants pass on this Windows
  environment).
- The 334-passed count is +83 over the MISSION-010 baseline (251) because
  MISSION-011 added four risk test modules (83 tests).

Coverage by module (test counts, VERIFIED by `Select-String` + full run):

| Test module | Count |
|-------------|-------|
| tests/structured_analysis_test.py | 41 |
| tests/worker_contract_test.py | 31 |
| tests/risk_engine_test.py | 30 |
| tests/recovery_engine_test.py | 29 |
| tests/security/path_security_test.py | 27 |
| tests/risk_level_test.py | 20 |
| tests/risk_policy_test.py | 18 |
| tests/security/adversarial_corpus_test.py | 17 |
| tests/security/worker_read_scope_test.py | 16 |
| tests/verification_executor_test.py | 15 |
| tests/risk_pipeline_test.py | 15 |
| tests/controller_decision_test.py | 13 |
| tests/worker_evidence_test.py | 13 |
| tests/worker_action_pipeline_test.py | 11 |
| tests/apply_verify_pipeline_test.py | 9 |
| tests/llm_provider_test.py | 9 |
| tests/worker_runtime_test.py | 7 |
| tests/patch_integrity_test.py | 6 |
| tests/worker_runtime_integration_test.py | 4 |
| tests/llm_provider_integration_test.py | 2 (gated, skipped) |
| tests/planner_contract_test.py | 1 |
| recovery_test.py (root) | 1 |

Not collected by pytest (script-style files): calculator_test.py,
context_test.py, decision_trace_test.py, hash_test.py, loop_test.py,
memory_event_test.py, memory_events_test.py, memory_test.py,
planner_test.py, read_after_test.py, registry_test.py, replay_test.py,
snapshot_test.py, strategy_dispatcher_test.py, tool_executor_test.py,
test_run.py.

Test directories `tests/chaos/`, `tests/integration/`, `tests/property/`,
`tests/unit/` exist but are EMPTY (VERIFIED by directory listing).

---

# Current Git State

```
Branch:            worker-action-pipeline
HEAD:              96ed72d (2026-08-11, "Integrate risk-aware worker action pipeline")
Working tree:      MISSION-011 close-out changes uncommitted (risk tests + recovery_assembly opt-in + docs)
Untracked files:   canonical audit docs (DECISION_LOG, MISSION_STATUS, PRODUCT_POSITIONING,
                   PROJECT_KNOWLEDGE_AUDIT, SECURITY_MODEL) — part of the 2026-08-11 audit
.gitignore:        excludes .env, .venv/, data/, __pycache__/, *.pyc
Tracked junk:      `git` (0 bytes), `kernel.txt` (stale Kernel draft),
                   simulation/domain/__pycache__/*.pyc,
                   simulation/security/__pycache__/*.pyc (tracked pyc artifacts)
Local env:         .env present with OPENROUTER_API_KEY (untracked; len 73)
```

`main` is 14 commits behind `worker-action-pipeline`. No release tag exists
after v0.5.0 for the worker-action-pipeline work.

---

# Known Limitations

VERIFIED where not marked:

1. **Risk engine (MISSION-011) is verified and closed; the gate stays
   DEFAULT OFF / explicit opt-in by design.** `RiskEngine`/`RiskPolicy`/
   `RiskLevel` have 83 passing tests; the gate is OFF unless both
   `risk_engine` and `risk_policy` are passed to `WorkerActionPipeline` or
   `build_recovery_agent` (D-021). The shipped assembly does not enable it
   because HIGH/CRITICAL would then require human approval, which is
   unimplemented (MISSION-012). Default-on is re-evaluated in MISSION-012.
2. **Human approval boundary is only a scaffold.** The pipeline consumes an
   `approval_store` with a `find_valid(fingerprint)` contract
   (`worker_action_pipeline.py:325`), but no `ApprovalStore` implementation
   exists anywhere in the codebase (VERIFIED by grep). HIGH/CRITICAL risk
   therefore fails closed at the approval stage until MISSION-012.
3. **Verification `compile`-only depth is tested but never policy-selected.**
   The MISSION-011 `verification_depth` switch exists in
   `apply_verify_pipeline.py:76`; the `compile` path is covered by tests
   (MISSION-011) but every non-deny policy level currently selects
   `compile+tests`.
4. **Recovery is not active in the default runtime** (opt-in `--recovery`).
5. **DecisionTrace is in-memory**; durable evidence is only the event log.
6. **Event store has no dedup**; re-running a task appends fresh events
   (recovery-level duplicate fingerprints are rejected by
   `BoundedRecoveryEngine`).
7. **`WorkerExecutor` hardcodes `task_id="worker-task"`** and
   `allowed_actions=("read","inspect","propose")`.
8. **Live LLM end-to-end behavior** is covered only by opt-in gated tests;
   full pipeline (apply/verify/recovery) with a real LLM is UNTESTED live.
9. **Docs drift:** README.md, CHANGELOG.md, docs/PROJECT_CONTEXT.md,
   docs/ROADMAP.md, docs/SESSION_NOTES.md, docs/MILESTONE-2.md still describe
   older versions/sprints.
10. **MISSION_LOG encoding corruption (mojibake)** in older entries, kept
    unchanged by policy.
11. **No CI**: `.github/workflows/` exists but is empty.
12. **No benchmarks, no concurrency/multi-agent tests**, no production
    configuration.

---

# Unresolved Issues

- MISSION-011 (Risk/Policy Engine) is now CLOSED/VERIFIED as a tested opt-in
  capability; whether the gate becomes default-on in the shipped assembly is
  deferred to MISSION-012 (depends on the approval store) — **UNKNOWN.**
- Whether recovery should become default (non-flag) behavior — explicitly a
  product decision (apply stays non-default by design).
- MISSION-009 was referenced as "state/documentation synchronization" but
  has no dedicated MISSION_LOG entry (commit `9b5c21e`).
- Whether the tracked `.pyc` artifacts and junk files (`git`, `kernel.txt`)
  should be removed from the repository.

---

# Immediate Next Work

Recommended (from audit findings, not a committed plan). MISSION-011 is
closed and is NOT re-listed here:

1. **Implement MISSION-012 Human Approval Boundary:** build a minimal
   `ApprovalStore` (persisted authorization events, fingerprint-keyed) with
   `find_valid(fingerprint)`, wire it to the pipeline's STAGE_APPROVAL, and
   decide how HIGH/CRITICAL risk flows to a human. This unblocks
   re-evaluating default-on risk gate (D-021).
2. Synchronize stale docs (README, CHANGELOG, PROJECT_CONTEXT,
   docs/ROADMAP) with the verified baseline.
3. Close MISSION-009 documentation.
4. Repository hygiene (tracked `.pyc`, junk files, stray directories).

---

# Notes

This document is synchronized with actual code, git history and the
2026-08-12 test run (334 passed, 9 skipped). Stale documentation must not
be trusted over code and git history.
