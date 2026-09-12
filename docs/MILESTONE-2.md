> **HISTORICAL SNAPSHOT** — this document is archived; it does not reflect the current state. Current truth-source: \docs/TANUQ_PROJECT_STATE.md\.

# MILESTONE-2

# Runtime Core Completion

Status:

In Progress

---

# Objective

Complete the Runtime Core.

After this milestone, the Runtime Core should remain stable.

Future features should be built around it instead of modifying it.

---

# Scope

The milestone includes:

- Event Store
- Reducer
- State
- Kernel
- Replay Engine
- Recovery Engine
- Snapshot
- Hash Chain
- Verification

---

# Excluded

The following are intentionally excluded:

- Dashboard
- REST API
- Multi-Agent
- Planner
- Memory Engine
- Decision Trace
- Enterprise Features

---

# Success Criteria

The Runtime Core should:

- Start correctly.
- Recover correctly.
- Replay deterministically.
- Produce identical state from identical events.
- Preserve event integrity.

---

# Engineering Rules

Runtime Core should become:

- Stable
- Deterministic
- Small
- Testable
- Provider Agnostic

---

# Long-Term Vision

The Runtime Core becomes the permanent foundation.

Everything else becomes a plugin around it.

Future capabilities should extend the platform without changing the core.

---

# Definition of Done

Runtime Core is complete when:

✓ Recovery Engine implemented

✓ Snapshot Recovery working

✓ Replay deterministic

✓ Existing tests passing

✓ Architecture documented

✓ RFC accepted

---

# Guiding Principle

Build the smallest core capable of supporting the largest future.