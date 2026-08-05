# ARCHITECTURE

---

# Purpose

The Event-Sourced AI Runtime is designed around a simple principle:

Every important AI action becomes an immutable event.

Instead of treating execution as temporary, the runtime preserves the complete execution history.

---

# High-Level Architecture

```text
User
 │
 ▼
Agent
 │
 ▼
Loop Engine
 │
 ▼
Kernel
 │
 ├── Reducer
 ├── Event Store
 ├── Replay Engine
 ├── Context Builder
 ├── Timeline
 └── Verify Chain
 │
 ▼
LLM Provider
 │
 ▼
AI Response
```

---

# Why Agent?

The Agent is responsible for coordinating the runtime.

Responsibilities:

- Receive user input
- Build context
- Call the LLM
- Record runtime events
- Coordinate Loop Engine

The Agent should not own application state.

---

# Why Loop Engine?

The Loop Engine represents execution flow.

Today:

Question

↓

Answer

Tomorrow:

Goal

↓

Planning

↓

Execution

↓

Verification

↓

Retry

↓

Completion

The Loop Engine should coordinate long-running AI tasks.

---

# Why Kernel?

The Kernel is the runtime core.

Responsibilities:

- Accept events
- Dispatch events
- Update runtime state
- Trigger reducers
- Store events

Business logic should remain outside the Kernel.

---

# Why Reducer?

Reducers rebuild state.

The current runtime state is always derived from events.

State should never become the primary source of truth.

Events are the source of truth.

---

# Why Event Store?

Every meaningful action is stored.

Benefits:

- Replay
- Audit
- Recovery
- Explainability

The Event Store is append-only.

Events are never modified.

---

# Why Replay?

Replay reconstructs runtime state from stored events.

Benefits:

- Crash recovery
- Deterministic execution
- Debugging
- Historical inspection

---

# Why Timeline?

Timeline is the runtime inspector.

It allows developers to understand:

- what happened,
- when it happened,
- and in which order.

Timeline is a debugging and observability tool.

---

# Why Verify Chain?

Every event references the previous event through a cryptographic hash.

Benefits:

- Tamper detection
- Integrity verification
- Audit confidence

Verification should always succeed before release.

---

# Why Context Builder?

The LLM should not rely on hidden memory.

Context Builder reconstructs the context from runtime state.

This keeps execution deterministic and reproducible.

---

# Design Principles

The project follows these principles:

- Event First
- Replay Everything
- Verify Before Release
- Small Verified Steps
- Keep Components Independent

---

# Component Responsibilities

| Component | Responsibility |
|-----------|----------------|
| Agent | Coordinates execution |
| Loop Engine | Controls execution flow |
| Kernel | Dispatches events |
| Reducer | Builds state |
| Event Store | Persists history |
| Replay Engine | Reconstructs state |
| Context Builder | Builds AI context |
| Timeline | Runtime inspection |
| Verify Chain | Integrity verification |

---

# Future Architecture

The current runtime answers questions.

Future versions will execute goals.

```text
Goal

↓

Planner

↓

Loop

↓

Workers

↓

Verification

↓

Replay

↓

Completion
```

The architecture is intentionally modular so future capabilities can be added without redesigning the runtime.

---

# Final Principle

The runtime should always answer four questions:

1. What happened?

2. Why did it happen?

3. Can it be replayed?

4. Can it be verified?

If the runtime cannot answer one of these questions, the architecture should be improved.