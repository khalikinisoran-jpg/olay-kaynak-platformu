# START HERE — Event-Sourcing Platform

## Project in One Paragraph

This repository implements an **event-sourced, deterministic, human-governed file-editing agent runtime**. Every user prompt becomes an immutable `Event` in `EventStore` (`events.jsonl` + `ChainAnchor` HMAC). The `Kernel` projects `State` via `Reducer`; `ContextBuilder` renders the last 10 `UNTRUSTED` conversation turns; an LLM proposes a `PatchProposal` (SHA-256 `path+action+reason+old/new+allowed_paths`); `PatchValidator` + `PathPolicy` checks `authoritative_scope`; `RiskEngine` classifies `SAFE`/`SUSPICIOUS HIGH`/`OPAQUE UNKNOWN`; `GovernanceEvaluator` (shared `RiskEngine`+`RiskPolicy`) decides `requires_human`; `ApprovalStore` enforces single-use `5-tuple`+`is patch` under `ledger._process_lock` with `ChainAnchor`; `ApplyAuthorization` (`is True` + `fingerprint`) + `FileApplier` (`mkstemp+fsync+replace`) writes only within `allowed_paths`. Evidence (`fingerprint` only) and recovery (`cap3`) never create authority. CLI thin wrappers (`apply`/`approve --pending`/`task --fake-analyzer`/`history`) expose the same pipeline with mechanical pending parity (`pending_proposals.json`, exact fingerprint). **P9 FINAL PASS @ `b2d6da7` (2026-08-25)** `b2d6da7234640e34fa349c067f56e23057053cf2` `1213 collected / 1200 passed / 13 skipped` — hosted Ubuntu ~88s / Windows ~182s via run 32805095789, local ~254s with 300s budget; 120s budget is NOT COMPLETED (historical P2.3-A `demo_cli.ps1` DENY→APPROVE→VERIFIED→replay DENY conserved as lineage). **Current repository HEAD is `9df6953`** (`9df6953b4a51071330d7584f0ed2b569f4ab434b`, 15 commits after P9): additional governed ExternalAction work exists after P9 — a durable governed external-action pipeline (`ExternalAction` / `ExternalActionPipeline` / `ExternalActionExecutor` / `ExternalOutcomeJournal` / `AttemptContext`) with runtime + CLI wiring (`agent_run.py external`); current local full-suite evidence at `9df6953`: `1278 collected / 1265 passed / 13 skipped / 0 failures` in 329.97s (local Windows run 2026-08-30; local evidence only — hosted CI verified at `ab77f9f` (push run `33301276606` SUCCESS: Ubuntu + Windows), NOT a production-correctness proof).

## Starting Path

Do **not** start with 70+ `MISSION-N*` forensic reports — they are historical evidence.

Read in order:

1. **Architecture:** `docs/ARCHITECTURE.md` — high-level `Kernel` → `EventStore` → `Approval` → `Apply` flow
2. **Authority / Security Model:** `docs/SECURITY_MODEL.md` — `PatchValidator` (scope `R1-R5`), `RiskEngine` (`os\[`+`generic get` `HIGH`), `GovernanceEvaluator`, `ApprovalStore` single-use, `ApplyAuthorization` (`is True`+`is patch`)
3. **Project State & Agent Procedure (current):** `docs/TANUQ_PROJECT_STATE.md` — live truth-source; `docs/TANUQ_SKILL.md` — agent working procedure. `docs/PROJECT_MASTER.md` / `docs/DECISIONS.md` are archived historical snapshots.
4. **Development / Testing:** `README.md` — setup and `pytest` instructions

## Core Principle

**LLM / conversation / memory / evidence are not authority.**

Real side effects (`FileApplier.apply` `os.replace` within `allowed_paths`) require the authoritative governed path: `PatchValidator` (`scope`) → `RiskEngine` (`HIGH→requires_human`) → `Governance` (recomputes risk) → `ApprovalStore` (`5-tuple`+`is patch`+`HIGH|CRITICAL` single-use) → `ApplyAuthorization` (`is True`+`fingerprint`) → `Apply`.

Trace metadata (`trace_id`, `fingerprint` in evidence) is **advisory**, never `is patch` `is True` `HIGH`.

## Repository Orientation

- **Core runtime:** `simulation/core/` (`kernel.py:71` `dispatch` `append→reducer→snapshot`, `reducer.py`, `state.py`), `simulation/persistence/` (`event_store.py:157`, `snapshot.py`, `chain_anchor.py:206`, `process_lock.py`)
- **Security / Governance:** `simulation/security/` (`risk_engine.py:300` `os\[`+`generic get`, `risk_policy.py:64`, `governance_evaluator.py:96`, `path_policy.py:41`, `hash_verifier.py:17`), `simulation/agent/approval/` (`approval_ledger.py:335`, `approval_store.py:288`), `simulation/agent/apply/` (`apply_executor.py:69`, `file_applier.py:50`)
- **Tests:** `tests/` `1278` collected `1265 passed / 13 skipped / 0 failures` in 329.97s (local Windows run at current HEAD `9df6953`, 2026-08-30; local evidence only — hosted CI verified at `ab77f9f` (push run `33301276606` SUCCESS: Ubuntu + Windows), NOT a production-correctness proof). Historical P9 FINAL PASS @ `b2d6da7` `b2d6da7234640e34fa349c067f56e23057053cf2`: `1213 collected / 1200 passed / 13 skipped / 0 failures` (hosted Ubuntu ~88s / Windows ~182s, local ~254s with 300s budget; 120s is NOT COMPLETED; foundation `24c72d0` 986 → 1213 → post-P9 ExternalAction additions to 1272)

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
# reproducible governed CLI demo — real CLI, no API key (P9 FINAL PASS @ b2d6da7 conserved; historical P2.3-A demo)
powershell -ExecutionPolicy Bypass -File demo_cli.ps1
# expected: DENIED WITHOUT APPROVAL -> APPROVED -> VERIFIED AFTER APPROVAL -> REPLAY DENIED -> HISTORY READ-ONLY -> OVERALL PASS
# demo — first working vertical slice (no external services, internal pipeline)
python demo_vertical_slice.py
# expected: Scenarios A LOW PASS, B HIGH denied→approved, C rollback; OVERALL PASS
# verify
.venv\Scripts\python -m compileall simulation tests
.venv\Scripts\python -m pytest -q
# expected at current HEAD 9df6953: 1265 passed, 13 skipped, 1278 collected (local Windows run 2026-08-30; local evidence only, hosted CI verified at `ab77f9f` (push run `33301276606` SUCCESS: Ubuntu + Windows))
# historical P9 FINAL PASS @ b2d6da7: 1200 passed, 13 skipped, 1213 collected (hosted Ubuntu ~88s / Windows ~182s via run 32805095789, local ~254s with 300s budget; 120s budget is NOT COMPLETED)
.venv\Scripts\python -m pytest -q tests/test_n6_mp_single_use.py tests/test_p22_exact_parity.py tests/test_cli_apply.py tests/test_cli_task.py tests/test_cli_observability.py -v
# expected: CLI parity + observability + approval + single-use (see P9 evidence; historical P2.3-A counts conserved as lineage)
```

No `Jaeger`/`Tempo`/`Redis`/`Kafka` required for the local suite (current HEAD `9df6953`: 1265 passed; historical P9 @ `b2d6da7`: 1200 passed).

## What Not to Read First

**Do not start with `MISSION-N*` / `LAYER-A-*` evidence reports** (`70+` `MISSION-N*` `10` `N27` `is NOW`). They are **forensic history**, not canonical onboarding.

They remain `EVIDENCE-OPTIONAL` `DO-NOT-COMMIT` (external archive), intentionally untracked. Canonical docs above are current at **HEAD `9df6953` (`9df6953b4a51071330d7584f0ed2b569f4ab434b`)** — current local full-suite evidence `1278 collected / 1265 passed / 13 skipped / 0 failures` in 329.97s (local Windows run 2026-08-30; local evidence only — hosted CI verified at `ab77f9f` (push run `33301276606` SUCCESS: Ubuntu + Windows)); historical P9 FINAL PASS baseline **`b2d6da7` (`b2d6da7234640e34fa349c067f56e23057053cf2`, 2026-08-25)** — `1213 collected / 1200 passed / 13 skipped` (hosted Ubuntu ~88s / Windows ~182s via run 32805095789, local ~254s with 300s budget; 120s is NOT COMPLETED); foundation `24c72d0` 986 → P7/P8/P9 → post-P9 governed ExternalAction additions to 1272; `MISSION-N*` remain archived at `C:\Projects\event-sourcing-platform-evidence-archive` (185 files = 144+19+22, N.92/N.94-R PASS). Historical P2.3-A `demo_cli.ps1` clean-clone `OVERALL PASS` (2026-08-23) conserved as lineage; the P9 exact-HEAD hosted CI evidence remains the historical verification baseline.

For historical decisions, summarized `docs/DECISIONS.md` is sufficient; read `MISSION-N*` only if auditing a specific forensic claim.
