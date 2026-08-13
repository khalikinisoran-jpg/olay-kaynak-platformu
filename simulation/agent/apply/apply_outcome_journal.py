"""Append-only, hash-chained apply intent / outcome journal (MISSION-019).

The governed runtime writes a patch to disk and *then* records the
outcome as evidence events through the Kernel. Those two steps are not
transactional, so a process crash between the file write and the event
append can leave a mutation on disk with no durable record. The journal
closes that gap with a separate, minimal, append-only file that records
the lifecycle of every apply *intent* around the real file write:

    INTENT -> APPLY_STARTED -> APPLIED  -> VERIFIED        (terminal)
                             -> APPLY_FAILED               (terminal)
                        APPLIED -> ROLLBACK_STARTED
                                     -> ROLLED_BACK        (terminal)
                                     -> ROLLBACK_FAILED    (terminal)

Design rules (from MISSION-019):

- The journal is a *durable outcome/audit* record. It is NOT an
  authorization input and never replaces the approval store, the
  apply boundary or the evidence chain (D-012 preserved).
- Records are secret-safe: never patch old/new content, only content
  SHA-256 hashes plus fingerprints, path, action, attempt, approval_id
  and short reasons.
- The file is append-only and hash-chained with the same SHA-256
  primitive as the event store and the approval ledger.
- Load is fail-closed: a missing, malformed, hash-broken or
  state-machine-invalid journal raises ``RuntimeError`` so the caller
  never operates on a journal it cannot trust (the startup
  reconciliation therefore fails closed on a corrupt journal).

Transitions are validated both at write time (session-local state) and
on ``load`` (authoritative full-file validation), so a duplicate intent,
an out-of-order transition or a record for an unknown intent is always
rejected.
"""

import json
import os
import threading
import uuid

from pathlib import Path

from simulation.security.hash_chain import HashChain


TYPE_INTENT = "intent"
TYPE_APPLY_STARTED = "apply_started"
TYPE_APPLIED = "applied"
TYPE_APPLY_FAILED = "apply_failed"
TYPE_VERIFIED = "verified"
TYPE_ROLLBACK_STARTED = "rollback_started"
TYPE_ROLLED_BACK = "rolled_back"
TYPE_ROLLBACK_FAILED = "rollback_failed"


_VALID_NEXT = {
    None: {TYPE_INTENT},
    TYPE_INTENT: {TYPE_APPLY_STARTED, TYPE_APPLY_FAILED},
    TYPE_APPLY_STARTED: {TYPE_APPLIED, TYPE_APPLY_FAILED},
    TYPE_APPLIED: {TYPE_VERIFIED, TYPE_ROLLBACK_STARTED},
    TYPE_VERIFIED: set(),
    TYPE_APPLY_FAILED: set(),
    TYPE_ROLLBACK_STARTED: {TYPE_ROLLED_BACK, TYPE_ROLLBACK_FAILED},
    TYPE_ROLLED_BACK: set(),
    TYPE_ROLLBACK_FAILED: set(),
}

TERMINAL_STATES = frozenset({
    TYPE_VERIFIED,
    TYPE_APPLY_FAILED,
    TYPE_ROLLED_BACK,
    TYPE_ROLLBACK_FAILED,
})


def _normalize_attempt(attempt):

    if (
        isinstance(attempt, int)
        and not isinstance(attempt, bool)
        and attempt >= 1
    ):

        return attempt

    return 1


class ApplyOutcomeJournal:

    """Durable, append-only journal for apply intent/outcome lifecycle."""

    def __init__(self, path="data/apply_journal.jsonl"):

        self.path = Path(path)

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self.path.touch(
            exist_ok=True
        )

        self._lock = threading.Lock()

        self._states = {}

        self._tail_hash = self._read_tail_hash()

        self._states = self._rebuild_states()

    def _read_tail_hash(self):

        """Last record's current_hash, or GENESIS for an empty file."""

        last_hash = "GENESIS"

        with open(
            self.path,
            "r",
            encoding="utf-8"
        ) as f:

            for line in f:

                if not line.strip():

                    continue

                try:

                    record = json.loads(line)

                except ValueError:

                    continue

                last_hash = record.get(
                    "current_hash",
                    last_hash,
                )

        return last_hash

    def _rebuild_states(self):

        """Rebuild the in-memory per-intent state machine from disk.

        Fail-closed: any structural violation raises ``RuntimeError``
        so a corrupt journal is detected at construction.
        """

        states = {}

        for record in self.load():

            states[record["intent_id"]] = record["record_type"]

        return states

    def record_intent(
        self,
        patch,
        attempt=1,
        approval_id="",
        reason="",
    ) -> str:

        """Open a new apply intent for a patch.

        Returns the fresh ``intent_id``. ``attempt`` is normalized to a
        positive integer. Content is stored as hashes only (secret-safe).
        """

        attempt = _normalize_attempt(attempt)

        intent_id = str(uuid.uuid4())

        old_hash = self._content_hash(
            getattr(patch, "old_content", "")
        )

        new_hash = self._content_hash(
            getattr(patch, "new_content", "")
        )

        self._append(
            TYPE_INTENT,
            intent_id,
            {
                "patch_fingerprint": patch.fingerprint(),
                "path": patch.path,
                "action": patch.action,
                "attempt": attempt,
                "approval_id": (
                    approval_id
                    if isinstance(approval_id, str)
                    else ""
                ),
                "old_content_hash": old_hash,
                "new_content_hash": new_hash,
                "reason": reason if isinstance(reason, str) else "",
            },
        )

        return intent_id

    def record_apply_started(self, intent_id, reason=""):

        self._append(
            TYPE_APPLY_STARTED,
            intent_id,
            {"reason": reason if isinstance(reason, str) else ""},
        )

    def record_applied(self, intent_id, reason=""):

        self._append(
            TYPE_APPLIED,
            intent_id,
            {"reason": reason if isinstance(reason, str) else ""},
        )

    def record_apply_failed(self, intent_id, reason=""):

        self._append(
            TYPE_APPLY_FAILED,
            intent_id,
            {"reason": reason if isinstance(reason, str) else ""},
        )

    def record_verified(self, intent_id, reason=""):

        self._append(
            TYPE_VERIFIED,
            intent_id,
            {"reason": reason if isinstance(reason, str) else ""},
        )

    def record_rollback_started(self, intent_id, reason=""):

        self._append(
            TYPE_ROLLBACK_STARTED,
            intent_id,
            {"reason": reason if isinstance(reason, str) else ""},
        )

    def record_rolled_back(self, intent_id, reason=""):

        self._append(
            TYPE_ROLLED_BACK,
            intent_id,
            {"reason": reason if isinstance(reason, str) else ""},
        )

    def record_rollback_failed(self, intent_id, reason=""):

        self._append(
            TYPE_ROLLBACK_FAILED,
            intent_id,
            {"reason": reason if isinstance(reason, str) else ""},
        )

    def _append(self, record_type, intent_id, body):

        with self._lock:

            previous = self._states.get(intent_id)

            allowed = _VALID_NEXT.get(previous, set())

            if record_type not in allowed:

                raise ValueError(
                    "Apply journal invalid transition: "
                    f"{previous!r} -> {record_type!r}"
                )

            record = {
                "record_type": record_type,
                "intent_id": intent_id,
                "previous_hash": self._tail_hash,
            }

            record.update(body)

            record["current_hash"] = HashChain.calculate(record)

            line = (
                json.dumps(
                    record,
                    ensure_ascii=False,
                )
                + "\n"
            ).encode("utf-8")

            with open(
                self.path,
                "ab"
            ) as f:

                f.write(line)

                f.flush()

                try:

                    os.fsync(f.fileno())

                except OSError:

                    pass

            self._tail_hash = record["current_hash"]

            self._states[intent_id] = record_type

    def load(self):

        """Fail-closed reload of all journal records.

        Returns records in append order after verifying the hash chain
        from GENESIS and the per-intent state machine. Any parse error,
        broken link, recomputed-hash mismatch, unknown record type,
        unknown intent or out-of-order transition raises
        ``RuntimeError``.
        """

        records = []

        previous_hash = "GENESIS"

        states = {}

        if not self.path.exists():

            return records

        with open(
            self.path,
            "r",
            encoding="utf-8"
        ) as f:

            for line_number, line in enumerate(
                f,
                start=1,
            ):

                if not line.strip():

                    continue

                try:

                    record = json.loads(line)

                except ValueError as exc:

                    raise RuntimeError(
                        "Apply journal is corrupted at "
                        f"line {line_number}: {exc}"
                    ) from exc

                if not isinstance(record, dict):

                    raise RuntimeError(
                        "Apply journal record at line "
                        f"{line_number} is not an object."
                    )

                if record.get(
                    "previous_hash"
                ) != previous_hash:

                    raise RuntimeError(
                        "Apply journal chain link broken "
                        f"at line {line_number}."
                    )

                body = {
                    key: value
                    for key, value in record.items()
                    if key != "current_hash"
                }

                if HashChain.calculate(
                    body
                ) != record.get("current_hash"):

                    raise RuntimeError(
                        "Apply journal hash mismatch at "
                        f"line {line_number}."
                    )

                previous_hash = record["current_hash"]

                record_type = record.get(
                    "record_type"
                )

                if record_type not in _VALID_NEXT:

                    raise RuntimeError(
                        "Apply journal unknown record type "
                        f"at line {line_number}: "
                        f"{record_type!r}"
                    )

                intent_id = record.get(
                    "intent_id"
                )

                if (
                    not isinstance(intent_id, str)
                    or not intent_id
                ):

                    raise RuntimeError(
                        "Apply journal record at line "
                        f"{line_number} is missing a "
                        "valid intent_id."
                    )

                previous_state = states.get(
                    intent_id
                )

                allowed = _VALID_NEXT.get(
                    previous_state,
                    set(),
                )

                if record_type not in allowed:

                    raise RuntimeError(
                        "Apply journal invalid transition "
                        f"at line {line_number}: "
                        f"{previous_state!r} -> "
                        f"{record_type!r}"
                    )

                states[intent_id] = record_type

                records.append(record)

        return records

    def intents(self, records):

        """Group loaded records by intent, preserving append order."""

        grouped = {}

        order = []

        for record in records:

            intent_id = record["intent_id"]

            if intent_id not in grouped:

                grouped[intent_id] = []

                order.append(intent_id)

            grouped[intent_id].append(record)

        return order, grouped

    @staticmethod
    def _content_hash(content) -> str:

        import hashlib

        return hashlib.sha256(
            (
                content
                if isinstance(content, str)
                else ""
            ).encode("utf-8")
        ).hexdigest()

    def tail_hash(self):

        """Last record's ``current_hash`` (``GENESIS`` for an empty file)."""

        return self._tail_hash
