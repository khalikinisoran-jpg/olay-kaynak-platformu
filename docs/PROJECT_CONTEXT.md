# PROJECT CONTEXT

---

# Project

Event-Sourced AI Runtime

---

# Mission

Build a trustworthy AI runtime using Event Sourcing.

Every meaningful action inside the runtime must become an immutable event.

The system must always be able to answer:

- What happened?
- Why did it happen?
- Can it be replayed?
- Can it be verified?
- Can the runtime recover?

The project values transparency and reproducibility over hidden state.

---

# Engineering Philosophy

This project is developed using small, verified steps.

No sprint is considered complete until:

- Replay succeeds
- Timeline reports HEALTHY
- Verify Chain reports VALID
- Runtime still works

Ideas inspire us.

Working software guides us.

Every sprint must leave the project in a working state.

---

# Current Version

v0.1.0-alpha

Status

Stable Core

Git Tag

v0.1.0-alpha

---

# Current Sprint

Sprint-7A

Loop Engine Foundation

Status

Completed

---

# Completed Milestones

Sprint-1

AI Runtime Foundation

Completed

Sprint-2

Replay Engine

Completed

Sprint-3

Snapshot Support

Completed

Sprint-4

Context Builder

Completed

Sprint-5A

Timeline Inspector

Completed

Sprint-5B

Global Sequence Engine

Completed

Sprint-6A

Hash Chain Verifier

Completed

Sprint-6B

Documentation

Completed

Sprint-7A

Loop Engine Foundation

Completed

---

# Current Runtime Architecture

User

↓

Agent

↓

Loop Engine

↓

Kernel

↓

Reducer

↓

Event Store

↓

Replay Engine

↓

Current State

↓

Context Builder

↓

LLM Provider

↓

AIResponseReceived

↓

Timeline

↓

Verify Chain

---

# Core Components

Event Store

Stores every event.

Append-only.

Replay Engine

Reconstructs runtime state.

Kernel

Dispatches events.

Reducer

Applies events.

Timeline

Displays runtime history.

Verify Chain

Checks hash integrity.

Context Builder

Creates runtime context.

Loop Engine

Controls long-running goals.

---

# Event Types

Current

UserQuestionReceived

AIResponseReceived

Planned

LoopStarted

LoopVerificationStarted

LoopCompleted

LoopFailed

WorkerRegistered

WorkerRemoved

TaskAssigned

TaskCompleted

---

# Verification Rules

Every sprint must pass

Timeline

python timeline.py

Expected

SYSTEM STATUS : HEALTHY

Verify Chain

python verify_chain.py

Expected

CHAIN STATUS : VALID

---

# Git Workflow

Before coding

git status

After coding

python timeline.py

python verify_chain.py

If both succeed

git add .

git commit

git push

Never leave the repository in a broken state.

---

# Documentation

README.md

Project overview

PROJECT_CONTEXT.md

Project memory

IDEAS.md

Research backlog

MILESTONE_v0.1.0-alpha.md

Release milestone

---

# Ideas Waiting

Loop Engineering

Event Query Engine

Decision Trace

Worker Runtime

Multi-Agent Runtime

Distributed Event Store

Plugin Architecture

Streaming Events

---

# Current Design Decisions

Event objects contain only domain data.

Hash information belongs to Event Store.

Replay rebuilds state.

Timeline validates execution.

Verify Chain validates integrity.

Loop Engine controls execution.

Agent coordinates components.

Kernel remains independent.

---

# Next Sprint

Sprint-7B

Loop Lifecycle Events

Goal

LoopStarted

LoopVerificationStarted

LoopCompleted

LoopFailed

must become normal runtime events.

Timeline should display loop lifecycle.

Replay should rebuild loop history.

---

# Long-Term Vision

Current

AI answers questions.

Future

AI receives goals.

↓

Plans.

↓

Executes.

↓

Verifies.

↓

Retries if necessary.

↓

Completes.

Every step becomes an event.

The runtime becomes self-explainable.

---

# Rules For Future Conversations

If a new conversation starts:

1.

Read this document first.

2.

Read README.md.

3.

Read IDEAS.md.

4.

Read the latest milestone.

5.

Continue from the current sprint.

Never redesign completed architecture without a clear reason.

Always preserve:

Replay

Timeline

Verify Chain

Working Runtime

---

# Project Motto

Building trustworthy AI through Event Sourcing, Replay, and Verification.

Every AI decision becomes an auditable event.

Ideas inspire us.

Working software guides us.

Small verified steps build great systems.