"""Detect-only reconciliation for external ambiguous outcomes (P10.3-R1).

Mirrors startup_reconciliation's contract: never mutates, never resends,
never auto-compensates, never upgrades UNKNOWN to VERIFIED without
trustworthy evidence.

For external actions the reconciliation problem is harder than files:
file outcomes can be inspected via content-hash comparison; external
actions have no local file to inspect when provider lacks status lookup.
This engine therefore classifies journal intents and reports orphans
without guessing.

Reports:
- ambiguous_intents: intents in TIMEOUT_UNKNOWN / AMBIGUOUS_UNKNOWN
- orphaned: non-terminal external intents (e.g. EXTERNAL_STARTED without terminal)
- success / failed counts

Detection is read-only; it never calls provider, never writes journal,
never writes file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from simulation.agent.apply.external_outcome_journal import (
    TERMINAL_STATES,
    AMBIGUOUS_STATES,
    ExternalOutcomeJournal,
)


@dataclass(frozen=True)
class ExternalReconciliationReport:
    total_intents: int
    success: int
    failed: int
    ambiguous: int
    orphaned_intents: tuple[str, ...] = field(default_factory=tuple)
    ambiguous_intents: tuple[str, ...] = field(default_factory=tuple)
    anomalies: tuple[str, ...] = field(default_factory=tuple)


class ExternalReconciliationEngine:
    """Detect-only reconciliation for external journals.

    SECURITY CONTRACT: detect-only. No file write, no provider call,
    no journal append, no approval consumption.
    """

    def __init__(self, journal: ExternalOutcomeJournal):
        self.journal = journal

    def detect(self) -> ExternalReconciliationReport:
        records = self.journal.load()
        # Group by intent (reusing journal's grouping not needed, we can map last state)
        states: dict[str, str] = {}
        for rec in records:
            states[rec["intent_id"]] = rec["record_type"]

        total = len(states)
        success = 0
        failed = 0
        ambiguous = 0
        orphaned: List[str] = []
        ambiguous_list: List[str] = []

        for intent_id, state in states.items():
            if state == "external_success":
                success += 1
            elif state == "external_failed":
                failed += 1
            elif state in ("external_timeout_unknown", "external_ambiguous_unknown"):
                ambiguous += 1
                ambiguous_list.append(intent_id)
            # Orphaned: non-terminal states (external_started, external_intent)
            if state not in TERMINAL_STATES:
                orphaned.append(intent_id)
            # AMBIGUOUS_STATES are also ambiguous
            if state in AMBIGUOUS_STATES:
                # already counted, but ensure in ambiguous_list
                if intent_id not in ambiguous_list:
                    ambiguous_list.append(intent_id)

        anomalies: List[str] = []
        # No additional anomaly detection needed for spike; keep empty.
        # Future could flag consumed approvals without terminal, duplicate idempotency etc.

        return ExternalReconciliationReport(
            total_intents=total,
            success=success,
            failed=failed,
            ambiguous=ambiguous,
            orphaned_intents=tuple(orphaned),
            ambiguous_intents=tuple(ambiguous_list),
            anomalies=tuple(anomalies),
        )
