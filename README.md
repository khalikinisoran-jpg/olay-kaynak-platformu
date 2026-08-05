# Event-Sourced AI Runtime

> **Building trustworthy AI through Event Sourcing, Replay, and Verification.**
>
> **Every AI decision becomes an auditable event.**

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

**v0.1.0-alpha**

Status:

✅ Stable Core

Git Tag

```
v0.1.0-alpha
```

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

Current documents:

- MILESTONE_v0.1.0-alpha.md
- IDEAS.md

Additional documentation will be added as the project evolves.

---

# Roadmap

## v0.2.0-alpha

Planned:

- [ ] Loop Engine
- [ ] Event Query Engine
- [ ] Decision Trace
- [ ] Runtime Console
- [ ] Worker Runtime

---

## Future

- [ ] Multi-Agent Runtime
- [ ] Distributed Event Runtime
- [ ] Streaming Event Bus
- [ ] Plugin Architecture
- [ ] Autonomous AI Loops

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