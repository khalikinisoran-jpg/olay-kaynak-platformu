"""Startup reconciliation for the apply-outcome journal (MISSION-019).

A crash can leave the filesystem and the durable record out of sync:
a patch was applied (or a rollback started) but the process died before
the outcome was journaled. This module reads the ``ApplyOutcomeJournal``
after a restart and *detects* such orphans without mutating anything:

- non-terminal intents are classified (applied-but-unverified,
  rollback-started, intent-only);
- when an allowed scope is configured, the target file is inspected
  and its current content hash is compared to the journaled old/new
  content hashes so an orphaned mutation is detected objectively;
- approvals that were consumed but whose intent never reached a
  terminal outcome are flagged.

SECURITY CONTRACT (MISSION-019): reconciliation is **detect-only**. It
never writes a file, never rolls anything back, and never re-authors an
apply. Repairing an orphaned mutation would be a filesystem mutation and
therefore requires an explicit, separately-authorized decision by the
operator; the startup path never performs it, so the approval boundary
is never bypassed ("recovery exists" is never a substitute for
authorization).

The journal load is fail-closed: a corrupt / malformed / hash-broken /
state-invalid journal raises ``RuntimeError`` instead of producing a
best-effort report.
"""

from dataclasses import dataclass, replace
from pathlib import Path

from simulation.agent.apply.apply_outcome_journal import (
    TERMINAL_STATES,
    TYPE_APPLIED,
    TYPE_APPLY_FAILED,
    TYPE_APPLY_STARTED,
    TYPE_INTENT,
    TYPE_ROLLBACK_FAILED,
    TYPE_ROLLBACK_STARTED,
    TYPE_ROLLED_BACK,
    TYPE_VERIFIED,
)

from simulation.security.path_policy import (
    PathPolicy,
)

CLASS_SUCCESS = "SUCCESS"
CLASS_FAILED_APPLY = "FAILED_APPLY"
CLASS_ROLLED_BACK = "ROLLED_BACK"
CLASS_ROLLBACK_FAILED = "ROLLBACK_FAILED"
CLASS_ORPHANED_APPLIED = "ORPHANED_APPLIED"
CLASS_ORPHANED_APPLY_START = "ORPHANED_APPLY_START"
CLASS_ORPHANED_ROLLBACK = "ORPHANED_ROLLBACK"
CLASS_INTENT_ONLY = "INTENT_ONLY"


@dataclass(frozen=True)
class IntentStatus:

    intent_id: str
    patch_fingerprint: str
    path: str
    action: str
    attempt: int
    approval_id: str
    state: str
    terminal: bool
    old_content_hash: str
    new_content_hash: str
    classification: str
    mutation_present: bool | None = None
    rollback_pending: bool = False


@dataclass(frozen=True)
class ReconciliationReport:

    intents: tuple[IntentStatus, ...]
    anomalies: tuple[str, ...]
    orphaned_mutations: tuple[IntentStatus, ...]
    consumed_approvals_without_outcome: tuple[str, ...]


def _classify(state, terminal):

    if terminal:

        if state == TYPE_VERIFIED:

            return CLASS_SUCCESS

        if state == TYPE_APPLY_FAILED:

            return CLASS_FAILED_APPLY

        if state == TYPE_ROLLED_BACK:

            return CLASS_ROLLED_BACK

        if state == TYPE_ROLLBACK_FAILED:

            return CLASS_ROLLBACK_FAILED

    if state == TYPE_APPLIED:

        return CLASS_ORPHANED_APPLIED

    if state == TYPE_APPLY_STARTED:

        return CLASS_ORPHANED_APPLY_START

    if state == TYPE_ROLLBACK_STARTED:

        return CLASS_ORPHANED_ROLLBACK

    if state == TYPE_INTENT:

        return CLASS_INTENT_ONLY

    return CLASS_INTENT_ONLY


def _content_hash(content) -> str:

    import hashlib

    return hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()


class ReconciliationEngine:

    """Detect-only analysis of journaled apply intents after a crash.

    ``detect()`` never mutates state; it classifies every intent and
    inspects in-scope target files to determine whether an orphaned
    mutation is actually present on disk.
    """

    def __init__(
        self,
        journal,
        allowed_paths=(),
        approval_store=None,
    ):

        self.journal = journal

        self.allowed_paths = tuple(allowed_paths)

        self.approval_store = approval_store

        self.path_policy = PathPolicy()

    def detect(self) -> ReconciliationReport:

        records = self.journal.load()

        order, grouped = self.journal.intents(records)

        intents = []

        anomalies = []

        for intent_id in order:

            intent_records = grouped[intent_id]

            first = intent_records[0]

            last = intent_records[-1]

            state = last["record_type"]

            terminal = state in TERMINAL_STATES

            classification = _classify(state, terminal)

            rollback_pending = state in (
                TYPE_APPLIED,
                TYPE_ROLLBACK_STARTED,
            )

            status = IntentStatus(
                intent_id=intent_id,
                patch_fingerprint=first.get(
                    "patch_fingerprint",
                    "",
                ),
                path=first.get("path", ""),
                action=first.get("action", ""),
                attempt=int(first.get("attempt", 1)),
                approval_id=first.get(
                    "approval_id",
                    "",
                ),
                state=state,
                terminal=terminal,
                old_content_hash=first.get(
                    "old_content_hash",
                    "",
                ),
                new_content_hash=first.get(
                    "new_content_hash",
                    "",
                ),
                classification=classification,
                rollback_pending=rollback_pending,
            )

            status = self._inspect_file(status)

            intents.append(status)

        consumed = self._consumed_approvals_without_outcome(
            intents,
        )

        anomalies.extend(
            self._duplicate_approval_anomalies(intents)
        )

        orphaned = tuple(
            status
            for status in intents
            if status.classification in (
                CLASS_ORPHANED_APPLIED,
                CLASS_ORPHANED_APPLY_START,
                CLASS_ORPHANED_ROLLBACK,
            )
        )

        return ReconciliationReport(
            intents=tuple(intents),
            anomalies=tuple(anomalies),
            orphaned_mutations=orphaned,
            consumed_approvals_without_outcome=consumed,
        )

    def _inspect_file(self, status):

        """Compare the on-disk file against the journaled hashes.

        Only in-scope files are inspected; anything else stays
        ``mutation_present=None`` (undetermined). Detection is
        read-only; nothing is ever written here.
        """

        if not self.allowed_paths:

            return status

        in_scope, _ = self.path_policy.check_scope(
            status.path,
            self.allowed_paths,
        )

        if not in_scope:

            return status

        path = Path(status.path)

        if not path.exists() or not path.is_file():

            return status

        try:

            current_hash = _content_hash(
                path.read_text(encoding="utf-8")
            )

        except Exception:

            return status

        if status.new_content_hash and (
            current_hash == status.new_content_hash
        ):

            return replace(
                status,
                mutation_present=True,
            )

        if status.old_content_hash and (
            current_hash == status.old_content_hash
        ):

            return replace(
                status,
                mutation_present=False,
            )

        return status

    def _consumed_approvals_without_outcome(self, intents):

        flagged = set()

        intent_approvals = {
            status.approval_id
            for status in intents
            if status.approval_id
        }

        terminal_approvals = {
            status.approval_id
            for status in intents
            if status.terminal and status.approval_id
        }

        for status in intents:

            if not status.approval_id:

                continue

            if status.terminal:

                continue

            flagged.add(status.approval_id)

        if self.approval_store is not None:

            consumed = getattr(
                self.approval_store,
                "consumed_ids",
                None,
            )

            if consumed is not None:

                for approval_id in consumed():

                    if not approval_id:

                        continue

                    if approval_id in terminal_approvals:

                        continue

                    if approval_id not in intent_approvals:

                        flagged.add(approval_id)

        return tuple(sorted(flagged))

    def _duplicate_approval_anomalies(self, intents):

        anomalies = []

        seen = {}

        for status in intents:

            if not status.approval_id:

                continue

            if status.approval_id in seen:

                anomalies.append(
                    "approval_id reused across intents: "
                    f"{status.approval_id} "
                    f"({seen[status.approval_id]} and "
                    f"{status.intent_id})"
                )

            else:

                seen[status.approval_id] = status.intent_id

        return anomalies

