# ADR-001

# Recovery Engine Orchestrates Replay

Status:

Accepted

---

## Context

The runtime needs a recovery mechanism.

ReplayEngine already performs deterministic replay.

Snapshots are available for reducing startup cost.

A design decision is required.

Should ReplayEngine become responsible for recovery?

Or should a dedicated RecoveryEngine orchestrate recovery?

---

## Decision

RecoveryEngine will orchestrate recovery.

ReplayEngine will remain responsible only for deterministic replay.

---

## Rationale

Replay is one responsibility.

Recovery is another responsibility.

Separating these concerns improves:

- readability
- maintainability
- testing
- future extensibility

---

## Consequences

ReplayEngine remains small.

RecoveryEngine becomes the startup strategy.

Future improvements become isolated.

Examples:

- snapshot recovery

- distributed recovery

- cloud recovery

- migration recovery

without modifying ReplayEngine.

---

## Alternatives Considered

Option A

ReplayEngine performs recovery.

Rejected.

Reason:

Violates Single Responsibility.

---

Option B

Kernel performs recovery.

Rejected.

Reason:

Kernel becomes too large.

---

Option C

RecoveryEngine orchestrates ReplayEngine.

Accepted.

---

## Long-Term Impact

Recovery becomes a pluggable strategy.

Replay remains deterministic forever.
