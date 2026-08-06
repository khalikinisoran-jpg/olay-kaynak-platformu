# RFC-001: Recovery Engine

**Status:** Draft

**Author:** Project Team

**Date:** 2026-08-06

---

# 1. Problem

The runtime currently rebuilds its entire state by replaying every event from the beginning.

This guarantees correctness but becomes increasingly expensive as the event log grows.

Although snapshots are already created, they are not used during runtime startup.

---

# 2. Motivation

The platform is designed around Event Sourcing.

Replay must remain deterministic.

However, startup performance should improve without compromising correctness.

A dedicated Recovery Engine separates recovery strategy from replay logic.

---

# 3. Goals

The Recovery Engine should:

- Detect whether a snapshot exists.
- Load the latest snapshot if available.
- Replay only the events that occurred after the snapshot.
- Produce the final runtime state.
- Keep ReplayEngine focused only on replay.

---

# 4. Non-Goals

The Recovery Engine will NOT:

- Modify events.
- Skip verification.
- Contain business logic.
- Replace ReplayEngine.

---

# 5. Proposed Architecture

Application Start

↓

Kernel

↓

Recovery Engine

↓

Snapshot Store

↓

Replay Engine

↓

Recovered State

---

# 6. Responsibilities

## Kernel

Coordinates startup.

Delegates recovery.

---

## Recovery Engine

Chooses the recovery strategy.

Combines snapshots and replay.

---

## Replay Engine

Rebuilds state from events.

Must remain deterministic.

---

## Snapshot Store

Stores and retrieves snapshots.

No recovery logic.

---

# 7. Acceptance Criteria

Recovery Engine is considered complete when:

- Runtime starts correctly without a snapshot.
- Runtime starts correctly with a snapshot.
- ReplayEngine remains unchanged.
- Existing tests continue to pass.
- State reconstruction remains deterministic.

---

# 8. Risks

Snapshot may become incompatible with future state models.

Mitigation:

Introduce snapshot versioning in a future RFC.

---

# 9. Future Extensions

Possible future improvements:

- Incremental snapshots.
- Snapshot compression.
- Snapshot integrity verification.
- Distributed recovery.
- Recovery metrics.

---

# 10. Decision

Recovery logic will live in its own component.

ReplayEngine will remain a deterministic replay component.

The architecture prioritizes long-term maintainability over short-term implementation speed.