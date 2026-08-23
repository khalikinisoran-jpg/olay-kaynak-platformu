# ROADMAP

Version: 2.0 — **SUPERSEDED as active direction on 2026-08-21** (historical phases preserved below with disclaimer)

Status: Historical — see Current Strategic Direction (A→C)

Last Updated: 2026-08-23 (HEAD `2f49d9f`, foundation `24c72d0` 986/974/12 conserved; P2.1/P2.2/P2.2-FP CLI + P2.3-A `demo_cli.ps1`)

> **Current strategic direction (2026-08-23, P2.3-A):** **A — Secure Coding Agent Runtime FIRST, then C — Controlled Productization.** General-purpose expansion (Multi-Agent / Distributed / Streaming / Autonomous) is **explicitly deferred**. Recent incremental milestones: **P2.1** governed CLI (`apply`/`approve`/`history`), **P2.2** natural task entry (`task --fake-analyzer`), **P2.2-FP** mechanical pending parity (`pending_proposals.json` + `approve --pending` exact fingerprint), **P2.3-A** reproducible PowerShell demo (`demo_cli.ps1`) + canonical doc sync to `2f49d9f`. Phases below are **not** the current active roadmap; retained as historical context. See `START-HERE.md` → `docs/ARCHITECTURE.md`.

Historical note: v2.0 planned Developer→Production→Enterprise→Autonomous progression. That progression is **not** current; current is Secure Runtime → Controlled Productization.

---

# Product Direction

The Event-Sourced AI Runtime is being built in phases.

Each phase has a single objective.

Features are added only after the underlying architecture is ready.

---

# Phase 1 — Developer Runtime

Status: In Progress

Goal:

Create a runtime that developers can use to build trustworthy AI applications.

Completed:

- Event Store
- Replay Engine
- Snapshot Recovery
- Verify Chain
- Planner
- Native Memory
- Memory Recall
- Executor Architecture
- Living Documentation

Remaining:

- Executor Registry
- Dispatcher Refactor
- Search Executor
- Weather Executor
- Multi-step Planning
- Goal Execution

Exit Criteria:

A developer can build an AI application entirely on top of the runtime.

---

# Phase 2 — Production Runtime

Status: Planned

Goal:

Prepare the runtime for production applications.

Features:

- Plugin API
- Configuration System
- Logging
- Metrics
- Observability
- Better Error Handling
- Runtime Diagnostics
- CI Pipeline
- Automated Tests

Exit Criteria:

The runtime can be safely used in production environments.

---

# Phase 3 — Enterprise Runtime

Status: Future

Goal:

Support regulated industries.

Features:

- Signed Event Chain
- Compliance Layer
- Audit Reports
- Deployment Profiles
- Enterprise Configuration
- Security Hardening

Exit Criteria:

The runtime satisfies enterprise deployment requirements.

---

# Phase 4 — Autonomous Runtime

Status: Vision

Goal:

Support autonomous AI execution.

Features:

- Goal Decomposition
- Autonomous Planning
- Worker Runtime
- Multi-Agent Coordination
- Long-Term Memory
- Learning Pipelines

Exit Criteria:

The runtime can coordinate long-running autonomous AI workflows.

---

# Sprint Focus

Sprint-18

Primary Goal:

Executor Registry

Nothing else.

When Sprint-18 is complete, the runtime should execute every strategy through a common registry instead of conditional logic.

---

# Long-Term Vision

The runtime should eventually become infrastructure that developers integrate into their own AI applications.

Models may change.

Tools may change.

The runtime remains.