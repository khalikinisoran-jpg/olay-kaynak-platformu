# START HERE — Event-Sourcing Platform

## Project in One Paragraph

This repository implements an **event-sourced, deterministic, human-governed file-editing agent runtime**. Every user prompt becomes an immutable `Event` in `EventStore` (`events.jsonl` + `ChainAnchor` HMAC). The `Kernel` projects `State` via `Reducer`; `ContextBuilder` renders the last 10 `UNTRUSTED` conversation turns; an LLM proposes a `PatchProposal` (SHA-256 `path+action+reason+old/new+allowed_paths`); `PatchValidator` + `PathPolicy` checks `authoritative_scope`; `RiskEngine` classifies `SAFE`/`SUSPICIOUS HIGH`/`OPAQUE UNKNOWN`; `GovernanceEvaluator` (shared `RiskEngine`+`RiskPolicy`) decides `requires_human`; `ApprovalStore` enforces single-use `5-tuple`+`is patch` under `ledger._process_lock` with `ChainAnchor`; `ApplyAuthorization` (`is True` + `fingerprint`) + `FileApplier` (`mkstemp+fsync+replace`) writes only within `allowed_paths`. Evidence (`fingerprint` only) and recovery (`cap3`) never create authority. CLI thin wrappers (`apply`/`approve --pending`/`task --fake-analyzer`/`history`) expose the same pipeline with mechanical pending parity (`pending_proposals.json`, exact fingerprint). P2.3-A verified reproducible via clean clone + clean venv + `demo_cli.ps1` DENY→APPROVE→VERIFIED→replay DENY (hosted CI not yet evidenced).

## Starting Path

Do **not** start with 70+ `MISSION-N*` forensic reports — they are historical evidence.

Read in order:

1. **Architecture:** `docs/ARCHITECTURE.md` — high-level `Kernel` → `EventStore` → `Approval` → `Apply` flow
2. **Authority / Security Model:** `docs/SECURITY_MODEL.md` — `PatchValidator` (scope `R1-R5`), `RiskEngine` (`os\[`+`generic get` `HIGH`), `GovernanceEvaluator`, `ApprovalStore` single-use, `ApplyAuthorization` (`is True`+`is patch`)
3. **Project State & Decisions:** `docs/PROJECT_MASTER.md` + `docs/DECISIONS.md` — current `50429ad` (foundation `24c72d0` / 71d2353 / 2f49d9f → 50429ad) `986 collected / 974 passed / 12 skipped / 0 failures` + P2.1/P2.2/P2.2-FP 22+9 CLI parity tests + P2.3-A clean-clone 41 ahead (2026-08-23, branch `worker-action-pipeline` clean; N.93 demo + P2.3-A `demo_cli.ps1` clean-clone verified locally + N.92 archive 185 PASS)
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
# prerequisites: Windows 10/11 + Python 3.12 + PowerShell 5.1 + git (no LLM key)
# clean reproduction (same as CI packaging smoke):
git clone https://github.com/khalikinisoran-jpg/olay-kaynak-platformu.git
cd olay-kaynak-platformu
git checkout worker-action-pipeline
python -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m pip install pytest==9.1.1
# reproducible governed CLI demo — real CLI, no API key (P2.3-A)
powershell -ExecutionPolicy Bypass -File demo_cli.ps1
# expected: DENIED WITHOUT APPROVAL -> APPROVED -> VERIFIED AFTER APPROVAL -> REPLAY DENIED -> HISTORY READ-ONLY -> OVERALL PASS
# clean-clone locally verified 2026-08-23 (vrepro + 9+7+6+5+48+10 PASS + demo OVERALL PASS); hosted CI not yet evidenced
# demo — first working vertical slice (no external services, internal pipeline)
python demo_vertical_slice.py
# expected: Scenarios A LOW PASS, B HIGH denied→approved, C rollback; OVERALL PASS
# verify
.venv\Scripts\python -m compileall simulation tests
.venv\Scripts\python -m pytest -q
# expected: 974 passed, 12 skipped, 986 collected (foundation conserved)
.venv\Scripts\python -m pytest -q tests/test_n6_mp_single_use.py tests/test_p22_exact_parity.py tests/test_cli_apply.py tests/test_cli_task.py tests/test_cli_observability.py -v
# expected: 10 + 9 + 7 + 6 + 5 + 48 passed (CLI parity + observability + approval + single-use, portable)
```

No `Jaeger`/`Tempo`/`Redis`/`Kafka` required for local `974`.

## What Not to Read First

**Do not start with `MISSION-N*` / `LAYER-A-*` evidence reports** (`70+` `MISSION-N*` `10` `N27` `is NOW`). They are **forensic history**, not canonical onboarding.

They remain `??` `EVIDENCE-OPTIONAL` `DO-NOT-COMMIT` (external archive), intentionally untracked. Canonical docs above are current at `50429ad` (foundation `24c72d0` / 71d2353 / 2f49d9f → 50429ad) on `worker-action-pipeline` (clean, `41` commits ahead of `main`, `986 collected`); `MISSION-N*` remain archived at `C:\Projects\event-sourcing-platform-evidence-archive` (185 files = 144+19+22, N.92/N.94-R PASS). P2.3-A `demo_cli.ps1` clean-clone verified locally 2026-08-23; hosted CI not yet evidenced.

For historical decisions, summarized `docs/DECISIONS.md` is sufficient; read `MISSION-N*` only if auditing a specific forensic claim.
