# ROADMAP

Version: 2.0 — **SUPERSEDED as active direction on 2026-08-21** (historical phases preserved below with disclaimer)

Status: Historical — see Current Strategic Direction (A→C)

Last Updated: 2026-08-30 (current HEAD `9df6953` `9df6953b4a51071330d7584f0ed2b569f4ab434b`, 15 commits after the historical P9 FINAL PASS baseline `b2d6da7` `b2d6da7234640e34fa349c067f56e23057053cf2`, 2026-08-25; current local full-suite evidence at `9df6953`: `1278 collected / 1265 passed / 13 skipped / 0 failures` in 329.97s — local Windows run 2026-08-30, NOT hosted CI, NOT a production-correctness proof; historical P9 FINAL PASS @ `b2d6da7`: `1213 collected / 1200 passed / 13 skipped / 0 failures`, hosted run 32805095789 Ubuntu ~88s / Windows ~182s, local ~254s with 300s budget; 120s is NOT COMPLETED; latest implementation lineage: `24c72d0` foundation 986 → P7 governed AgentSession → P8 multi-file atomicity → P9 FINAL PASS → `b2d6da7` / `1213` → post-P9 governed ExternalAction pipeline → `d42736d` / `1272` → P10.2 docs sync + P10.3 hygiene + post-P10.3 p5 authority/integrity fixes → `9df6953` / `1278`)

> **Current strategic direction (2026-08-30, current HEAD `9df6953`):** **A — Secure Coding Agent Runtime FIRST, then C — Controlled Productization.** General-purpose expansion (Multi-Agent / Distributed / Streaming / Autonomous) is **explicitly deferred**. Current local full-suite evidence at `9df6953`: `1278 collected / 1265 passed / 13 skipped / 0 failures` in 329.97s (local Windows run 2026-08-30; local evidence only — NOT hosted CI, NOT a production-correctness proof). Historical P9 FINAL PASS @ `b2d6da7` `b2d6da7234640e34fa349c067f56e23057053cf2`: `1213 collected / 1200 passed / 13 skipped / 0 failures` (hosted run 32805095789 Ubuntu ~88s / Windows ~182s, local ~254s with 300s budget; 120s is NOT COMPLETED). Latest implementation lineage: `24c72d0` foundation 986 → P7 governed AgentSession → P8 multi-file atomicity → P9 FINAL PASS → `b2d6da7` / `1213` → post-P9 governed ExternalAction pipeline → `d42736d` / `1272` → P10.2 documentation synchronization completed (`07326ce`); P10.3 hygiene consolidation executed (`2150fe3` / `acef450` / `8452e0e`); post-P10.3 p5 authority/integrity fixes recorded as an OPERATOR-label series (P10.4-P10.6: `f60fa13` / `31c46c2` / `9df6953`) — these labels are NOT canonical roadmap phases; the label collision with the canonical "P10.4 packaging hardening" item is preserved as AMBIGUITY. Phases below are **not** the current active roadmap; retained as historical context. See `START-HERE.md` → `docs/ARCHITECTURE.md`.

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