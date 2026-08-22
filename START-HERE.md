# START HERE — Event-Sourcing Platform

## Project in One Paragraph

This repository implements an **event-sourced, deterministic, human-governed file-editing agent runtime**. Every user prompt becomes an immutable `Event` in `EventStore` (`events.jsonl` + `ChainAnchor` HMAC). The `Kernel` projects `State` via `Reducer`; `ContextBuilder` renders the last 10 `UNTRUSTED` conversation turns; an LLM proposes a `PatchProposal` (SHA-256 `path+action+reason+old/new+allowed_paths`); `PatchValidator` + `PathPolicy` checks `authoritative_scope`; `RiskEngine` classifies `SAFE`/`SUSPICIOUS HIGH`/`OPAQUE UNKNOWN`; `GovernanceEvaluator` (shared `RiskEngine`+`RiskPolicy`) decides `requires_human`; `ApprovalStore` enforces single-use `5-tuple`+`is patch` under `ledger._process_lock` with `ChainAnchor`; `ApplyAuthorization` (`is True` + `fingerprint`) + `FileApplier` (`mkstemp+fsync+replace`) writes only within `allowed_paths`. Evidence (`fingerprint` only) and recovery (`cap3`) never create authority.

## Starting Path

Do **not** start with 70+ `MISSION-N*` forensic reports — they are historical evidence.

Read in order:

1. **Architecture:** `docs/ARCHITECTURE.md` — high-level `Kernel` → `EventStore` → `Approval` → `Apply` flow
2. **Authority / Security Model:** `docs/SECURITY_MODEL.md` — `PatchValidator` (scope `R1-R5`), `RiskEngine` (`os\[`+`generic get` `HIGH`), `GovernanceEvaluator`, `ApprovalStore` single-use, `ApplyAuthorization` (`is True`+`is patch`)
3. **Project State & Decisions:** `docs/PROJECT_MASTER.md` + `docs/DECISIONS.md` — current `71d2353` (foundation `24c72d0` / 7d274bf) `986 collected / 974 passed / 12 skipped / 0 failures` (N.94/N.94-R 2026-08-22, branch `worker-action-pipeline` clean; N.89 portability, N.91 cleanup, N.93 demo, N.92 archive 185 PASS)
4. **Development / Testing:** `README.md` — setup and `pytest` instructions

## Core Principle

**LLM / conversation / memory / evidence are not authority.**

Real side effects (`FileApplier.apply` `os.replace` within `allowed_paths`) require the authoritative governed path: `PatchValidator` (`scope`) → `RiskEngine` (`HIGH→requires_human`) → `Governance` (recomputes risk) → `ApprovalStore` (`5-tuple`+`is patch`+`HIGH|CRITICAL` single-use) → `ApplyAuthorization` (`is True`+`fingerprint`) → `Apply`.

Trace metadata (`trace_id`, `fingerprint` in evidence) is **advisory**, never `is patch` `is True` `HIGH`.

## Repository Orientation

- **Core runtime:** `simulation/core/` (`kernel.py:71` `dispatch` `append→reducer→snapshot`, `reducer.py`, `state.py`), `simulation/persistence/` (`event_store.py:157`, `snapshot.py`, `chain_anchor.py:206`, `process_lock.py`)
- **Security / Governance:** `simulation/security/` (`risk_engine.py:300` `os\[`+`generic get`, `risk_policy.py:64`, `governance_evaluator.py:96`, `path_policy.py:41`, `hash_verifier.py:17`), `simulation/agent/approval/` (`approval_ledger.py:335`, `approval_store.py:288`), `simulation/agent/apply/` (`apply_executor.py:69`, `file_applier.py:50`)
- **Tests:** `tests/` `986` collected `974 passed / 12 skipped` (`test_n6 10`, `a26 11`, `multiprocess 9`, `path_security 42`, `adversarial_corpus`) — MISSION N.55 verified

## First Commands

All verified from current repository (`pyproject.toml` `testpaths: tests`):

```bash
# create venv and install (once)
python -m venv .venv
.venv\Scripts\python -m pip install -e .
# demo — first working vertical slice (no external services)
python demo_vertical_slice.py
# expected: Scenarios A LOW PASS, B HIGH denied→approved, C rollback; OVERALL PASS
# verify
.venv\Scripts\python -m compileall simulation tests
.venv\Scripts\python -m pytest -q
# expected: 974 passed, 12 skipped, 986 collected
.venv\Scripts\python -m pytest -q tests/test_n6_mp_single_use.py -v
# expected: 10 passed (N-New-01 single-use anchored, portable)
.venv\Scripts\python -m pytest -q tests/security/a26_env_reference_regression_test.py -v
# expected: 11 passed (A26 HIGH)
```

No `Jaeger`/`Tempo`/`Redis`/`Kafka` required for local `974`.

## What Not to Read First

**Do not start with `MISSION-N*` / `LAYER-A-*` evidence reports** (`70+` `MISSION-N*` `10` `N27` `is NOW`). They are **forensic history**, not canonical onboarding.

They remain `??` `EVIDENCE-OPTIONAL` `DO-NOT-COMMIT` (external archive), intentionally untracked. Canonical docs above are current at `71d2353` (foundation `24c72d0` / 7d274bf) on `worker-action-pipeline` (clean, `35` commits ahead of `main`, `986 collected`); `MISSION-N*` remain archived at `C:\Projects\event-sourcing-platform-evidence-archive` (185 files = 144+19+22, N.92/N.94-R PASS).

For historical decisions, summarized `docs/DECISIONS.md` is sufficient; read `MISSION-N*` only if auditing a specific forensic claim.
