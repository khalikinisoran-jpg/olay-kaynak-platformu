# PLATFORM ARCHITECTURE

---

# Purpose

This document describes the high-level architecture of the Event-Sourced AI Runtime.

It focuses on responsibilities, boundaries, and interactions between the major components of the platform.

This is intentionally technology-agnostic.

The architecture should remain stable even if implementation details change.

---

# Platform Vision

The platform is designed to become a trustworthy runtime for AI systems.

Instead of treating AI responses as temporary outputs, every meaningful action becomes a verifiable event.

The runtime is responsible for:

- Recording
- Replaying
- Recovering
- Explaining
- Verifying

AI providers are interchangeable.

The runtime is the product.

---

# Core Principles

The architecture follows these principles:

- Event First
- Replay Everything
- Verification Before Trust
- Provider Agnostic
- Small Stable Core
- Modular Growth

---

# High-Level Architecture

```text
                 User
                   │
                   ▼
                Agent
                   │
                   ▼
                Kernel
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
   Event Store   Replay    Loop Engine
        │
        ▼
 Snapshot Layer
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
 Decision Trace
```

---

# Platform Layers

## Layer 1

Runtime Core

Responsibilities:

- Kernel
- Reducer
- State
- Events

The Runtime Core coordinates the platform.

Business logic should remain minimal.

---

## Layer 2

Persistence

Responsibilities:

- Event Store
- Snapshot Store

Provides durable storage.

No business logic.

---

## Layer 3

Recovery

Responsibilities:

- Replay Engine
- Recovery Engine (planned)

Responsible for rebuilding runtime state.

---

## Layer 4

Context

Responsibilities:

- Conversation History
- Context Builder

Transforms runtime state into model context.

---

## Layer 5

AI Providers

Responsibilities:

- OpenRouter
- OpenAI
- Claude
- Gemini
- Local Models

Providers remain replaceable.

---

## Layer 6

Explainability

Responsibilities:

- Timeline
- Decision Trace
- Event Query (planned)

Allows humans to inspect runtime behavior.

---

## Layer 7

Security

Responsibilities:

- Hash Chain
- Verification
- Event Integrity
- Future Digital Signatures

Trust must be verifiable.

---

# Component Responsibilities

## Kernel

Coordinates runtime execution.

Should avoid accumulating business logic.

---

## Reducer

Applies Events.

Produces State.

Must remain deterministic.

---

## Event Store

Stores immutable events.

Append-only.

---

## Replay Engine

Rebuilds state from events.

Should remain deterministic.

---

## Snapshot Layer

Stores recovery checkpoints.

Future Recovery Engine will use snapshots before replaying remaining events.

---

## Context Builder

Transforms runtime state into AI-readable context.

---

## Decision Trace

Explains why the runtime produced a specific response.

Current status:

Foundation.

---

# Planned Components

Recovery Engine

Purpose:

Recover runtime using snapshots plus remaining events.

---

Event Query Engine

Purpose:

Search runtime history efficiently.

Examples:

- Find events by type
- Find events after sequence
- Recent events

---

Memory Engine

Purpose:

Select relevant historical information.

Avoid sending the full conversation to the LLM.

---

Policy Engine

Purpose:

Apply runtime rules before model execution.

---

Planner

Purpose:

Break goals into executable plans.

---

Worker Runtime

Purpose:

Execute planned actions.

---

# Architectural Rules

New components should:

- Have one responsibility.
- Be independently testable.
- Minimize coupling.
- Preserve replayability.
- Preserve determinism.

---

# Long-Term Goal

Transform the project into a production-grade AI Runtime Platform.

The platform should eventually support:

- Explainable AI
- Recoverable AI
- Verifiable AI
- Multi-Agent AI
- Enterprise AI

without changing the Runtime Core.

---

# Closing Statement

The architecture is intentionally modular.

Complexity should grow outward.

The Runtime Core should remain small, deterministic, and trustworthy.

Everything else is built around it.