# Event-Sourced AI Runtime

> **Building trustworthy AI through Event Sourcing, Replay, and Verification.**
>
> **Every AI decision becomes an auditable event.**

> **Current canonical identity (2026-08-23, `worker-action-pipeline` @ `50429ad`):** An **event-sourced, deterministic, human-governed file-editing agent runtime.** Flow: `LLM / User / Memory → Change Intent / Patch Proposal → Deterministic Validation → Risk + Governance → Human Approval when required → Single-Use Authorization → Atomic File Apply → Verification / Event Evidence / Recovery`. Core principle: **LLM MAY PROPOSE. LLM MUST NOT BE THE FINAL AUTHORITY.** See `START-HERE.md` → `docs/ARCHITECTURE.md` + `docs/SECURITY_MODEL.md`. Verified baseline: **`986 collected / 974 passed / 12 skipped / 0 failures`** (foundation N.55 at 24c72d0 conserved; HEAD 71d2353 adds N.89 portability, N.91 cleanup, N.93 demo, N.92/N.94-R archive 185 PASS; HEAD 2f49d9f adds P2.1 governed CLI, P2.2 natural task entry, P2.2-FP pending exact parity; HEAD 50429ad adds P2.3-A reproducible demo + doc sync, clean-clone verified locally).

An experimental AI runtime that treats every meaningful AI interaction as an immutable event.

Instead of storing only the latest state, the runtime records every action, making AI systems replayable, recoverable, auditable, and verifiable.

---

# Vision

Traditional AI systems focus on the current state.

This project explores a different philosophy.

Every important action becomes an immutable event.

Instead of asking:

> **"What is the current state?"**

the runtime can answer:

- How did we get here?
- Which events produced the current state?
- Can every decision be replayed?
- Can the runtime recover after a crash?
- Has any event been modified?
- Can the AI inspect its own history?

The long-term goal is to build trustworthy AI systems whose behavior can always be reconstructed, verified, and explained.

---

# Why Event Sourcing?

Most AI applications discard history and only keep the latest result.

This project does the opposite.

History becomes the source of truth.

Benefits include:

- Immutable history
- Complete audit trail
- Deterministic replay
- Crash recovery
- State reconstruction
- Explainable AI
- Runtime verification
- Future multi-agent support

---

# Current Version

**0.6.0** (package) — canonical branch **`worker-action-pipeline` @ `50429ad`** (`feat(demo): reproducible governed CLI demo and canonical state sync (P2.3-A)`)

Status: Active Development — **Foundation + N.94/N.94-R verified 2026-08-22, P2.1/P2.2/P2.2-FP verified 2026-08-23, P2.3-A reproducible baseline verified 2026-08-23 via clean clone + clean venv + `demo_cli.ps1`** (`986 collected / 974 passed / 12 skipped / 0 failures` foundation conserved; CLI parity 9 + CLI apply/task 13 + observability 5 + boundary 48 + mp single-use 10 pass locally and in clean clone; hosted CI not yet evidenced)

Git Tag (latest release): `v0.5.0` — `worker-action-pipeline` is `41` commits ahead of `main` (no release tag after `v0.5.0` for this branch; `0.6.0` declared in `pyproject.toml` but not yet tagged/released)

---

# Current Features

## Event Store

- Immutable JSONL event storage
- Append-only architecture
- Event persistence
- Replay-ready history

---

## Replay Engine

- Runtime recovery
- State reconstruction
- Full event replay
- Crash recovery

---

## Global Sequence Engine

- Automatic sequence generation
- Sequential consistency
- Runtime validation

---

## Hash Chain

Each stored event contains:

- previous_hash
- current_hash

This creates a cryptographic chain capable of detecting event tampering.

---

## Hash Chain Verifier

Verifies:

- previous_hash
- current_hash
- chain integrity
- event consistency

Run:

```bash
python verify_chain.py
```

---

## Timeline Inspector

Displays:

- Complete event history
- Payload inspection
- Event statistics
- Sequence validation
- Runtime summary

Run:

```bash
python timeline.py
```

---

## Context Builder

Builds runtime context directly from the reconstructed state.

Supports context-aware AI responses.

---

## AI Runtime

Current supported events:

- UserQuestionReceived
- AIResponseReceived

Every interaction becomes part of the Event Store.

---

# Runtime Status

| Component | Status |
|------------|--------|
| Event Store | ✅ |
| Replay Engine | ✅ |
| Global Sequence | ✅ |
| Hash Chain | ✅ |
| Verify Chain | ✅ |
| Timeline Inspector | ✅ |
| Context Builder | ✅ |
| AI Runtime | ✅ |

---

# Core Architecture

```text
                 User
                   │
                   ▼
        UserQuestionReceived
                   │
                   ▼
                Kernel
                   │
         ┌─────────┴─────────┐
         │                   │
         ▼                   ▼
      Reducer          Event Store
                             │
      ┌──────────────────────┼──────────────────────┐
      ▼                      ▼                      ▼
 Replay Engine          Hash Chain          Timeline Inspector
      │
      ▼
 Current State
      │
      ▼
 Context Builder
      │
      ▼
  LLM Provider
      │
      ▼
AIResponseReceived
```

---

# Project Structure

```text
simulation/
│
├── agent/
├── core/
├── persistence/
├── replay/
├── security/
│
docs/
│
data/
│
timeline.py
verify_chain.py
agent_run.py
```

---

# Quick Start

Clone the repository

```bash
git clone https://github.com/khalikinisoran-jpg/olay-kaynak-platformu.git
```

Move into the project

```bash
cd olay-kaynak-platformu
```

Install dependencies

```bash
pip install -r requirements.txt
```

Run the AI runtime

```bash
python agent_run.py
```

Inspect the timeline

```bash
python timeline.py
```

Verify hash integrity

```bash
python verify_chain.py
```

---

# Verification Workflow

Every development sprint follows the same workflow.

```text
Idea

↓

Design

↓

Implementation

↓

Replay

↓

Timeline

↓

Verify Chain

↓

Git Commit

↓

Release
```

No feature is considered complete until:

- Replay succeeds
- Timeline reports HEALTHY
- Verify Chain reports VALID
- Runtime continues to operate correctly

---

# Example Runtime

```text
User

↓

UserQuestionReceived

↓

Kernel

↓

Event Store

↓

Context Builder

↓

LLM

↓

AIResponseReceived

↓

Replay Ready
```

---

# Documentation

Documentation is located inside the **docs/** directory.

Canonical entry point: **`START-HERE.md`** → `docs/ARCHITECTURE.md` (implemented flow) → `docs/SECURITY_MODEL.md` (verified boundaries) → `docs/PROJECT_MASTER.md` + `docs/PROJECT_STATE.md` → `docs/ROADMAP.md` (current direction).

**Demo:** `python demo_vertical_slice.py` — first working vertical slice of the governed patch pipeline (no external services; see docstring for Scenarios A/B/C).

**Reproducible governed CLI demo (P2.3-A):** `powershell -ExecutionPolicy Bypass -File demo_cli.ps1` — uses only the real CLI (`task`/`approve --pending`/`history`), deterministic `--fake-analyzer` (no LLM key), demonstrates HIGH-risk DENY → pending approval → VERIFIED → replay DENY (single-use fingerprint binding). See Quick Start below.

**Visible product experience (P5):** `python demo_p5.py` or `powershell -ExecutionPolicy Bypass -File demo_p5.ps1` — uses the **real P5 localhost UI/service path** (`p5/server.py` view layer, `http://127.0.0.1:8766`) over the existing governed pipeline; shows proposal → HIGH approval-required → approve via canonical `ApprovalStore` → VERIFIED → replay DENY → adversarial spoof DENY (UI never writes directly, LLM claims untrusted). Also runnable as `python -m p5.server --port 8765` then open `http://127.0.0.1:8765/`.

Additional historical docs exist under `docs/` but **canonical docs above are the source of current truth**; `MISSION-N*` reports are archived outside the repo.

---

# Reproducible Governed CLI Demo (P2.3-A)

This is a governed file-editing runtime demonstration, not a production autonomous agent.

- Worker proposes via `--fake-analyzer` (deterministic, no API key). Replace with real LLM analyzer later; governance boundary is unchanged.
- Risk is system-derived (`RiskEngine`): `hello`→`hello fixed` = LOW auto-apply; `api_key = "sk-..."` = HIGH requires human approval.
- Approval binds to exact `PatchProposal` fingerprint (`path+action+reason+old/new+allowed_paths` SHA-256) and is single-use; different proposal or replay is DENY.
- Run from repository root in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File demo_cli.ps1
# expected: DENIED WITHOUT APPROVAL -> APPROVED -> VERIFIED AFTER APPROVAL -> REPLAY DENIED -> HISTORY READ-ONLY -> OVERALL PASS
```

The script creates a temp workspace, writes `demo.txt` as exactly `hello` (no BOM), runs the HIGH-risk `task`, `approve --pending`, re-runs `task`, tests replay, and prints `history`. Exit 0 + `OVERALL PASS` only if all governance checks observed.

**Clean reproduction (prerequisites explicit):** `Windows 10/11 + Python 3.12 + PowerShell 5.1 + git`. Clean steps: `git clone <repo> && cd <repo> && python -m venv .venv && .venv\Scripts\python -m pip install -e . && .venv\Scripts\python -m pip install pytest==9.1.1 && .venv\Scripts\python -m pytest tests/test_p22_exact_parity.py tests/test_cli_apply.py tests/test_cli_task.py tests/test_cli_observability.py -v && powershell -ExecutionPolicy Bypass -File demo_cli.ps1`. Clean-clone verified locally 2026-08-23 (fresh `vrepro` venv + `pip install -e .` + 9+7+6+5+48+10 PASS + demo `OVERALL PASS`); hosted CI not yet evidenced — see `START-HERE.md` First Commands.

# P5 Visible Product Experience (view layer, not authority)

Local UI is a **view layer** over the existing governed runtime (`p5/server.py`, stdlib `http.server`). Start:

```powershell
python -m p5.server --host 127.0.0.1 --port 8765
# open http://127.0.0.1:8765/  (Goal → Proposal → Governance → Approve → Execute → Verify → History)
python demo_p5.py
# expected: A LOW VERIFIED -> B HIGH APPROVAL_REQUIRED -> approve -> VERIFIED -> C REPLAY DENIED -> D ADVERSARIAL DENIED -> OVERALL PASS
```

What it demonstrates (real UI/service path, not mocks): proposal visible (target/fingerprint/diff/risk/approval-required), governance state (`PROPOSED`/`APPROVAL_REQUIRED`/`DENIED`/`VERIFIED`/`ROLLED_BACK`), canonical approval via `ApprovalStore` exact fingerprint (single-use, replay DENY preserved), execution via `WorkerActionPipeline` only (UI never calls `FileApplier`/`open(...,w)` on target), read-only history from `ApplyOutcomeJournal`. LLM claims (`approved`, `bypass_governance`, `verification_passed`) remain untrusted and are shown only as data, never as decisions. Known limitations: localhost only, no auth, no production DB, governed path unchanged — see `p5/server.py` header.

---

# Roadmap

> **Current strategic direction (2026-08-21):** **A — Secure Coding Agent Runtime FIRST, then C — Controlled Productization.** General-purpose runtime expansion (Multi-Agent / Distributed / Autonomous) is **explicitly deferred**. See `docs/ROADMAP.md` (v2.0 superseded; current direction is A→C).

## Recently verified (worker-action-pipeline @ 60b37ff + P5; foundation 24c72d0)

- [x] Worker Action Pipeline (Patch Proposal → Validation → Risk → Governance → Approval → Apply → Verify → Recovery)
- [x] Deterministic Risk + Governance + Single-Use Approval + Atomic Apply
- [x] Event Store Trust Anchor (ChainAnchor), Provenance, Evidence
- [x] Human-Governed Runtime (`--governed` / `--recovery`)
- [x] Vertical-slice demo `python demo_vertical_slice.py` — LOW pass, HIGH denied→approved, rollback (N.93, real `WorkerActionPipeline`)
- [x] Historical evidence archive 185 files (144 MISSION-N* + 19 LAYER-A-* + 22 remaining = 185, PRESERVED_RELOCATED, N.92 + N.94-R independent repro PASS)
- [x] P2.1 governed CLI (`apply`/`approve`/`history`/`status` thin wrappers over `WorkerActionPipeline`, `agent_run.py:154`) — 7 CLI apply + 5 observability tests
- [x] P2.2 natural task entry (`task --goal --fake-analyzer` -> Worker -> governed pipeline, `agent_run.py:216`) — 6 CLI task tests
- [x] P2.2-FP mechanical pending parity (`pending_proposals.json` + `approve --pending` exact fingerprint, `agent_run.py:534`) — 9 parity tests (HIGH denied→pending→verified→replay DENY, newline/BOM handling)
- [x] P2.3-A reproducible governed CLI baseline (`demo_cli.ps1` DENY→APPROVE→VERIFIED→replay DENY, clean clone + clean venv `pip install -e .` 9+7+6+5+48+10 PASS) — verified locally 2026-08-23
- [x] P3 adversarial proposals (20 tests, 8 scenarios) — real repo, zero bypass
- [x] P4 LLM as untrusted proposer (hardened `LLMCodeAnalyzer` spoof strip + 13 deterministic + live smoke `deepseek` hello→hello fixed) — proposer != authority
- [x] P5 visible product experience (`p5/server.py` localhost view layer + `demo_p5.py` A-D via real UI path) — no direct write, UI != authority, 7 UI tests, HIGH→approve→VERIFIED→replay DENY→spoof DENY, history read-only

Historical v2.0 Phases 1-4 (Developer→Production→Enterprise→Autonomous) are retained in `docs/ROADMAP.md` as context; they are not the active plan.

## Next (controlled productization, not general expansion)

- [x] P5 visible product experience (`demo_p5.py` via real UI/service path, localhost `p5/server.py`)
- [ ] Packaging / CI hardening on current governed runtime (hosted runner evidence still missing)
- [ ] Controlled productization decisions (no autonomous/multi-agent expansion)

---

# Engineering Philosophy

This project follows a simple engineering principle.

Ideas inspire us.

Working software guides us.

Every new feature must preserve:

- Replay
- Timeline
- Verify Chain
- Runtime Stability

Every great idea first becomes a document.

Every document becomes a sprint.

Every sprint becomes working software.

---

# Release History

## v0.1.0-alpha

Initial public milestone.

Includes:

- Event Store
- Replay Engine
- Global Sequence Engine
- Hash Chain
- Verify Chain
- Timeline Inspector
- Context Builder
- AI Runtime
- Documentation
- Milestone
- Engineering Ideas Backlog

---

# License

MIT License

---

# Project Motto

> **Building trustworthy AI through Event Sourcing, Replay, and Verification.**

> **Every AI decision becomes an auditable event.**

> **Ideas inspire us. Working software guides us.**