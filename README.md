# Event-Sourced AI Runtime

> Every AI decision becomes an auditable event.
## Vision

This project explores a different approach to AI systems.

Instead of treating an AI response as something temporary, every important action is stored as an immutable event.

This enables:

- Replayable AI
- Auditable AI
- Recoverable AI
- Deterministic execution
## Core Architecture

```text
User
 │
 ▼
Agent
 │
 ▼
LLM Provider
 │
 ▼
Kernel
 │
 ├── Reducer
 ├── Event Store
 ├── Snapshot
 └── Replay
```
## Design Principles

- Event First
- Replay Everything
- Provider Agnostic
- Open Architecture
- Simplicity Wins
## Roadmap

### Sprint 1
- [ ] Stable Runtime
- [ ] CLI
- [ ] Event Replay
- [ ] Snapshot Recovery

### Sprint 2
- [ ] Memory Engine
- [ ] Workspace
- [ ] Policy Engine

### Sprint 3
- [ ] Multi-Agent Runtime
- [ ] Planner
- [ ] Tool Calling