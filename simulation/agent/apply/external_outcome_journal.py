"""External outcome journal — governed ambiguous-result foundation (P10.3-R1).

Mirrors ApplyOutcomeJournal's hash-chain and fail-closed semantics but
with explicit ambiguous-result states required by the audit:

    INTENT -> EXTERNAL_STARTED -> EXTERNAL_SUCCESS          (terminal, known success)
                              -> EXTERNAL_FAILED           (terminal, known failure)
                              -> EXTERNAL_TIMEOUT_UNKNOWN  (terminal, ambiguous)
                              -> EXTERNAL_AMBIGUOUS_UNKNOWN(terminal, ambiguous)

MODEL B (P10.3-C2b) adds stable intent lineage:

    TIMEOUT/AMBIGUOUS -> HUMAN_DECISION_REQUIRED -> ATTEMPT_OPENED -> STARTED -> ...

No ROLLBACK branch for external actions in this spike — external
compensation is explicitly *not* implemented (see §7). The journal is
durable outcome/audit only, never authorization input (D-012 preserved).

Records are secret-safe: payload/idempotency_key stored as SHA-256 hashes
only, plus provider/operation/fingerprint/approval_id/attempt/reason.

File is append-only, hash-chained via HashChain.calculate, load is
fail-closed (hash mismatch / chain break / invalid transition raises
RuntimeError), matching ApplyOutcomeJournal guarantees. This allows
startup reconciliation to be detect-only while still observing durable
ambiguous states.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path

from simulation.persistence.process_lock import EventStoreBusyError, _ProcessFileLock
from simulation.security.hash_chain import HashChain


TYPE_EXTERNAL_INTENT = "external_intent"
TYPE_EXTERNAL_STARTED = "external_started"
TYPE_EXTERNAL_SUCCESS = "external_success"
TYPE_EXTERNAL_FAILED = "external_failed"
TYPE_EXTERNAL_TIMEOUT_UNKNOWN = "external_timeout_unknown"
TYPE_EXTERNAL_AMBIGUOUS_UNKNOWN = "external_ambiguous_unknown"
TYPE_HUMAN_DECISION_REQUIRED = "human_decision_required"
TYPE_ATTEMPT_OPENED = "attempt_opened"


_VALID_NEXT = {
    None: {TYPE_EXTERNAL_INTENT},
    TYPE_EXTERNAL_INTENT: {TYPE_EXTERNAL_STARTED, TYPE_EXTERNAL_FAILED},
    TYPE_EXTERNAL_STARTED: {
        TYPE_EXTERNAL_SUCCESS,
        TYPE_EXTERNAL_FAILED,
        TYPE_EXTERNAL_TIMEOUT_UNKNOWN,
        TYPE_EXTERNAL_AMBIGUOUS_UNKNOWN,
    },
    TYPE_EXTERNAL_TIMEOUT_UNKNOWN: {TYPE_HUMAN_DECISION_REQUIRED},
    TYPE_EXTERNAL_AMBIGUOUS_UNKNOWN: {TYPE_HUMAN_DECISION_REQUIRED},
    TYPE_HUMAN_DECISION_REQUIRED: {TYPE_ATTEMPT_OPENED},
    TYPE_ATTEMPT_OPENED: {TYPE_EXTERNAL_STARTED},
    TYPE_EXTERNAL_SUCCESS: set(),
    TYPE_EXTERNAL_FAILED: set(),
}

TERMINAL_STATES = frozenset(
    {
        TYPE_EXTERNAL_SUCCESS,
        TYPE_EXTERNAL_FAILED,
        TYPE_EXTERNAL_TIMEOUT_UNKNOWN,
        TYPE_EXTERNAL_AMBIGUOUS_UNKNOWN,
    }
)

AMBIGUOUS_STATES = frozenset(
    {
        TYPE_EXTERNAL_TIMEOUT_UNKNOWN,
        TYPE_EXTERNAL_AMBIGUOUS_UNKNOWN,
    }
)


def _hash_content(text: str) -> str:
    return hashlib.sha256(
        (text if isinstance(text, str) else "").encode("utf-8")
    ).hexdigest()


def _validate_attempt(attempt: int) -> int:
    if not isinstance(attempt, int) or isinstance(attempt, bool) or not (1 <= attempt <= 3):
        raise ValueError(f"attempt must be int 1..3, got {attempt!r}")
    return attempt


@dataclass(frozen=True)
class AttemptContext:
    intent_id: str
    attempt: int
    synthetic: object
    approval_id: str
    previous_hash: str
    expected_previous_attempt: int


class ExternalOutcomeJournal:
    """Durable, append-only journal for external intent/outcome lifecycle."""

    def __init__(self, path="data/external_journal.jsonl"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch(exist_ok=True)
        self._lock = threading.Lock()
        self._process_lock = _ProcessFileLock(self.path, timeout=_ProcessFileLock.DEFAULT_TIMEOUT)
        self._file_size = 0
        self._states: dict[str, str] = {}
        self._tail_hash = "GENESIS"
        # Use process lock for initial tail read to avoid torn read
        try:
            with self._process_lock:
                self._tail_hash = self._read_tail_hash()
                self._file_size = self._snapshot_file_size()
                self._states = self._rebuild_states()
        except EventStoreBusyError:
            # Fallback to non-locked read (fail-closed on busy)
            self._tail_hash = self._read_tail_hash()
            self._states = self._rebuild_states()

    def _snapshot_file_size(self) -> int:
        try:
            return os.path.getsize(self.path)
        except OSError:
            return 0

    def _sync_if_stale(self):
        current_size = self._snapshot_file_size()
        if current_size == self._file_size:
            return
        self._tail_hash = self._read_tail_hash()
        self._states = self._rebuild_states()
        self._file_size = current_size

    def _read_tail_hash(self) -> str:
        last_hash = "GENESIS"
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                last_hash = record.get("current_hash", last_hash)
        return last_hash

    def _rebuild_states(self) -> dict[str, str]:
        states: dict[str, str] = {}
        for record in self.load():
            states[record["intent_id"]] = record["record_type"]
        return states

    # ---- writers ----

    def record_intent(self, *args, **kwargs) -> str:
        """Record external intent.

        Frozen MODEL B signature:

            record_intent(intent_id: str, action: ExternalAction, attempt: int, approval_id: str) -> str

        For backward compatibility with MODEL A spike tests, also accepts:

            record_intent(action: ExternalAction, attempt: int, approval_id: str, reason: str)

        where action is first positional ExternalAction and intent_id is generated via uuid4.
        New code should use intent_id first form.
        """
        # Detect new vs old signature
        intent_id = None
        action = None
        attempt = 1
        approval_id = ""
        reason = ""

        # New signature: intent_id is str, action has fingerprint
        if len(args) >= 1 and isinstance(args[0], str) and len(args) >= 2 and hasattr(args[1], "fingerprint"):
            intent_id = args[0]
            action = args[1]
            if len(args) > 2:
                attempt = args[2]
            else:
                attempt = kwargs.get("attempt", 1)
            if len(args) > 3:
                approval_id = args[3]
            else:
                approval_id = kwargs.get("approval_id", "")
            if len(args) > 4:
                reason = args[4]
            else:
                reason = kwargs.get("reason", "")
        elif len(args) >= 1 and hasattr(args[0], "fingerprint"):
            # Old signature: record_intent(action, attempt, approval_id, reason)
            action = args[0]
            if len(args) > 1:
                attempt = args[1]
            else:
                attempt = kwargs.get("attempt", 1)
            if len(args) > 2:
                approval_id = args[2]
            else:
                approval_id = kwargs.get("approval_id", "")
            if len(args) > 3:
                reason = args[3]
            else:
                reason = kwargs.get("reason", "")
            # Old path generates new intent_id
            intent_id = str(uuid.uuid4())
        else:
            #kwargs-only new style
            intent_id = kwargs.get("intent_id")
            action = kwargs.get("action")
            attempt = kwargs.get("attempt", 1)
            approval_id = kwargs.get("approval_id", "")
            reason = kwargs.get("reason", "")
            if intent_id is None and action is not None and hasattr(action, "fingerprint"):
                # old kwargs style without intent_id
                intent_id = str(uuid.uuid4())
            if intent_id is None:
                raise ValueError("intent_id and action required")

        attempt = _validate_attempt(attempt)
        # secret-safe hashes
        payload_hash = _hash_content(getattr(action, "payload", ""))
        idem_hash = _hash_content(getattr(action, "idempotency_key", ""))
        self._append(
            TYPE_EXTERNAL_INTENT,
            intent_id,
            {
                "fingerprint": action.fingerprint(),
                "provider": getattr(action, "provider", ""),
                "operation": getattr(action, "operation", ""),
                "attempt": attempt,
                "approval_id": approval_id if isinstance(approval_id, str) else "",
                "payload_hash": payload_hash,
                "idempotency_hash": idem_hash,
                "reason": reason if isinstance(reason, str) else "",
            },
        )
        return intent_id

    def record_started(self, intent_id: str, reason: str = ""):
        self._append(TYPE_EXTERNAL_STARTED, intent_id, {"reason": reason if isinstance(reason, str) else ""})

    def record_success(self, intent_id: str, reason: str = ""):
        self._append(TYPE_EXTERNAL_SUCCESS, intent_id, {"reason": reason if isinstance(reason, str) else ""})

    def record_failed(self, intent_id: str, reason: str = ""):
        self._append(TYPE_EXTERNAL_FAILED, intent_id, {"reason": reason if isinstance(reason, str) else ""})

    def record_timeout_unknown(self, intent_id: str, reason: str = ""):
        self._append(TYPE_EXTERNAL_TIMEOUT_UNKNOWN, intent_id, {"reason": reason if isinstance(reason, str) else ""})

    def record_ambiguous_unknown(self, intent_id: str, reason: str = ""):
        self._append(TYPE_EXTERNAL_AMBIGUOUS_UNKNOWN, intent_id, {"reason": reason if isinstance(reason, str) else ""})

    def record_human_decision(self, intent_id: str, reason: str = ""):
        self._append(TYPE_HUMAN_DECISION_REQUIRED, intent_id, {"reason": reason if isinstance(reason, str) else ""})

    def open_attempt(
        self,
        intent_id: str,
        expected_current_attempt: int,
        new_approval_id: str,
    ) -> AttemptContext:
        """Open next attempt for stable intent_id.

        Durable transition: TIMEOUT/AMBIGUOUS -> HUMAN_DECISION_REQUIRED(attempt=expected) -> ATTEMPT_OPENED(attempt=new)
        where new = expected + 1, 1<=expected<3, new<=3.

        Holds process_lock for reload + CAS + both appends atomically.
        Returns AttemptContext for pipeline to use.
        """
        if not isinstance(intent_id, str) or not intent_id:
            raise ValueError("intent_id must be non-empty string")
        expected_current_attempt = _validate_attempt(expected_current_attempt)
        if expected_current_attempt >= 3:
            raise ValueError(f"expected_current_attempt must be <3, got {expected_current_attempt}")
        new_attempt = expected_current_attempt + 1
        _validate_attempt(new_attempt)
        if not isinstance(new_approval_id, str) or not new_approval_id:
            raise ValueError("new_approval_id must be non-empty string")

        with self._lock:
            with self._process_lock:
                self._sync_if_stale()
                # Reload states inside lock
                # Find latest state and attempt for this intent_id
                # Need to scan records for this intent_id to find latest attempt
                # Use load() to get all records and find last for intent_id
                records = self.load()
                latest_state = None
                latest_attempt = None
                for rec in records:
                    if rec.get("intent_id") == intent_id:
                        latest_state = rec.get("record_type")
                        # attempt is stored in intent record and attempt_opened record
                        if "attempt" in rec:
                            latest_attempt = rec.get("attempt")
                # For initial intent, latest_state should be TIMEOUT or AMBIGUOUS and latest_attempt == expected
                if latest_state not in (TYPE_EXTERNAL_TIMEOUT_UNKNOWN, TYPE_EXTERNAL_AMBIGUOUS_UNKNOWN):
                    raise ValueError(f"open_attempt requires latest state TIMEOUT/AMBIGUOUS, got {latest_state!r}")
                if latest_attempt != expected_current_attempt:
                    raise ValueError(f"expected_current_attempt {expected_current_attempt} != latest {latest_attempt}")
                # Append HUMAN then ATTEMPT_OPENED atomically
                # Need to synthesize minimal patch for AttemptContext.synthetic? Keep None for T-B1, caller will derive
                # For T-B1, synthetic is not needed to be real PatchProposal; keep None or build from stored fingerprint? Keep None.
                # But AttemptContext expects synthetic; for T-B1 we can set None.
                # Record HUMAN
                self._append_locked(TYPE_HUMAN_DECISION_REQUIRED, intent_id, {"attempt": expected_current_attempt, "approval_id": new_approval_id, "reason": "human decision required"})
                # Record ATTEMPT_OPENED
                self._append_locked(TYPE_ATTEMPT_OPENED, intent_id, {"attempt": new_attempt, "approval_id": new_approval_id, "reason": "attempt opened"})
                # Build AttemptContext
                # previous_hash is tail after ATTEMPT_OPENED
                ctx = AttemptContext(
                    intent_id=intent_id,
                    attempt=new_attempt,
                    synthetic=None,
                    approval_id=new_approval_id,
                    previous_hash=self._tail_hash,
                    expected_previous_attempt=expected_current_attempt,
                )
                return ctx

    def start_opened_attempt(
        self,
        context: AttemptContext,
        action,
        approval_id: str,
    ) -> None:
        """Validate retry context and append external_started for the retry attempt.

        Frozen validation (fail-closed, no provider call, no new intent):
        1. context refers to current durable retry attempt.
        2. intent_id matches durable lineage.
        3. attempt matches durable opened attempt.
        4. opening-record / previous-hash lineage evidence matches.
        5. approval_id matches supplied approval_id and context.approval_id.
        6. durable retry state is valid for starting (must be ATTEMPT_OPENED).
        7. action fingerprint matches original intent fingerprint.

        Only after successful validation appends external_started.
        """
        if not isinstance(context, AttemptContext):
            raise ValueError("context must be AttemptContext")
        if not isinstance(context.intent_id, str) or not context.intent_id:
            raise ValueError("context intent_id invalid")
        _validate_attempt(context.attempt)
        if not isinstance(context.approval_id, str) or not context.approval_id:
            raise ValueError("context approval_id invalid")
        if not isinstance(context.previous_hash, str) or not context.previous_hash:
            raise ValueError("context previous_hash invalid")
        if not isinstance(approval_id, str) or not approval_id:
            raise ValueError("approval_id must be non-empty string")
        # approval correlation: supplied must equal context's approval_id
        if approval_id != context.approval_id:
            raise ValueError(f"approval_id {approval_id!r} != context approval_id {context.approval_id!r}")
        if not hasattr(action, "fingerprint") or not callable(getattr(action, "fingerprint")):
            raise ValueError("action must have fingerprint()")
        action_fp = action.fingerprint()

        with self._lock:
            with self._process_lock:
                self._sync_if_stale()
                records = self.load()
                # Find latest state and latest attempt record for this intent
                latest_state = None
                latest_attempt = None
                latest_approval_id = None
                intent_fingerprint = None
                # Also track the attempt_opened record's hash
                attempt_opened_hash = None
                for rec in records:
                    if rec.get("intent_id") == context.intent_id:
                        latest_state = rec.get("record_type")
                        if "attempt" in rec and rec.get("record_type") in (TYPE_EXTERNAL_INTENT, TYPE_ATTEMPT_OPENED, TYPE_HUMAN_DECISION_REQUIRED):
                            # track latest attempt value
                            latest_attempt = rec.get("attempt") if rec.get("record_type") == TYPE_ATTEMPT_OPENED else latest_attempt
                            # for human/attempt_opened we want latest
                            if rec.get("record_type") == TYPE_ATTEMPT_OPENED:
                                latest_attempt = rec.get("attempt")
                                latest_approval_id = rec.get("approval_id")
                                attempt_opened_hash = rec.get("current_hash")
                        # fingerprint from intent
                        if rec.get("record_type") == TYPE_EXTERNAL_INTENT and intent_fingerprint is None:
                            intent_fingerprint = rec.get("fingerprint")
                        elif rec.get("record_type") == TYPE_EXTERNAL_INTENT:
                            # Keep first intent fingerprint; subsequent intents shouldn't exist for same intent_id
                            pass
                # More precise latest_attempt extraction: scan last attempt_opened
                # Re-derive latest_attempt/approval for this intent_id from last attempt_opened/human
                # Find last record for intent_id to get latest_state already done
                # Now find last attempt_opened's attempt/approval
                last_attempt_opened = None
                for rec in reversed(records):
                    if rec.get("intent_id") == context.intent_id and rec.get("record_type") == TYPE_ATTEMPT_OPENED:
                        last_attempt_opened = rec
                        break
                if last_attempt_opened is not None:
                    latest_attempt = last_attempt_opened.get("attempt")
                    latest_approval_id = last_attempt_opened.get("approval_id")
                    attempt_opened_hash = last_attempt_opened.get("current_hash")
                # Also find first intent fingerprint if not found via direct scan
                if intent_fingerprint is None:
                    for rec in records:
                        if rec.get("intent_id") == context.intent_id and rec.get("record_type") == TYPE_EXTERNAL_INTENT:
                            intent_fingerprint = rec.get("fingerprint")
                            break

                # 1/2/3: intent_id must exist and attempt matches durable opened
                if latest_state is None:
                    raise ValueError(f"intent_id {context.intent_id!r} not found in journal")
                # 6: state must be ATTEMPT_OPENED ready for STARTED
                if latest_state != TYPE_ATTEMPT_OPENED:
                    raise ValueError(f"start requires state ATTEMPT_OPENED, got {latest_state!r}")
                if latest_attempt != context.attempt:
                    raise ValueError(f"context attempt {context.attempt} != durable opened attempt {latest_attempt}")
                # 5: approval_id correlation (already checked supplied==context, now check durable)
                if latest_approval_id != context.approval_id:
                    raise ValueError(f"context approval_id {context.approval_id!r} != durable {latest_approval_id!r}")
                # 4: previous-hash lineage evidence
                # context.previous_hash must equal the durable attempt_opened hash for this intent
                if context.previous_hash != attempt_opened_hash:
                    raise ValueError(f"context previous_hash mismatch: {context.previous_hash!r} != {attempt_opened_hash!r}")
                # Also expected_previous_attempt consistency
                if context.expected_previous_attempt != context.attempt - 1:
                    raise ValueError(f"expected_previous_attempt {context.expected_previous_attempt} != attempt-1 {context.attempt-1}")
                # 7: fingerprint match
                if intent_fingerprint is None:
                    raise ValueError("original intent fingerprint not found")
                if action_fp != intent_fingerprint:
                    raise ValueError(f"action fingerprint {action_fp!r} != original {intent_fingerprint!r}")

                # All validated → append external_started atomically
                self._append_locked(TYPE_EXTERNAL_STARTED, context.intent_id, {"reason": "retry execution started", "attempt": context.attempt, "approval_id": context.approval_id})

    def _append_locked(self, record_type: str, intent_id: str, body: dict):
        """Inner append without acquiring locks (caller holds both)."""
        previous = self._states.get(intent_id)
        allowed = _VALID_NEXT.get(previous, set())
        if record_type not in allowed:
            raise ValueError(
                f"External journal invalid transition: {previous!r} -> {record_type!r}"
            )
        record = {
            "record_type": record_type,
            "intent_id": intent_id,
            "previous_hash": self._tail_hash,
        }
        record.update(body)
        record["current_hash"] = HashChain.calculate(record)
        line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
        with open(self.path, "ab") as f:
            f.write(line)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        self._tail_hash = record["current_hash"]
        self._states[intent_id] = record_type
        self._file_size = self._snapshot_file_size()

    # ---- core ----

    def _append(self, record_type: str, intent_id: str, body: dict):
        with self._lock:
            with self._process_lock:
                self._sync_if_stale()
                previous = self._states.get(intent_id)
                allowed = _VALID_NEXT.get(previous, set())
                if record_type not in allowed:
                    raise ValueError(
                        f"External journal invalid transition: {previous!r} -> {record_type!r}"
                    )
                record = {
                    "record_type": record_type,
                    "intent_id": intent_id,
                    "previous_hash": self._tail_hash,
                }
                record.update(body)
                record["current_hash"] = HashChain.calculate(record)
                line = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
                with open(self.path, "ab") as f:
                    f.write(line)
                    f.flush()
                    try:
                        os.fsync(f.fileno())
                    except OSError:
                        pass
                self._tail_hash = record["current_hash"]
                self._states[intent_id] = record_type
                self._file_size = self._snapshot_file_size()

    def load(self):
        records = []
        previous_hash = "GENESIS"
        states: dict[str, str] = {}
        if not self.path.exists():
            return records
        with open(self.path, "r", encoding="utf-8") as f:
            for line_number, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except ValueError as exc:
                    raise RuntimeError(
                        f"External journal is corrupted at line {line_number}: {exc}"
                    ) from exc
                if not isinstance(record, dict):
                    raise RuntimeError(
                        f"External journal record at line {line_number} is not an object."
                    )
                if record.get("previous_hash") != previous_hash:
                    raise RuntimeError(
                        f"External journal chain link broken at line {line_number}."
                    )
                body = {k: v for k, v in record.items() if k != "current_hash"}
                if HashChain.calculate(body) != record.get("current_hash"):
                    raise RuntimeError(
                        f"External journal hash mismatch at line {line_number}."
                    )
                previous_hash = record["current_hash"]
                record_type = record.get("record_type")
                if record_type not in _VALID_NEXT:
                    raise RuntimeError(
                        f"External journal unknown record type at line {line_number}: {record_type!r}"
                    )
                intent_id = record.get("intent_id")
                if not isinstance(intent_id, str) or not intent_id:
                    raise RuntimeError(
                        f"External journal record at line {line_number} is missing a valid intent_id."
                    )
                previous_state = states.get(intent_id)
                allowed = _VALID_NEXT.get(previous_state, set())
                if record_type not in allowed:
                    raise RuntimeError(
                        f"External journal invalid transition at line {line_number}: {previous_state!r} -> {record_type!r}"
                    )
                states[intent_id] = record_type
                records.append(record)
        return records

    def intents(self, records):
        grouped = {}
        order = []
        for record in records:
            intent_id = record["intent_id"]
            if intent_id not in grouped:
                grouped[intent_id] = []
                order.append(intent_id)
            grouped[intent_id].append(record)
        return order, grouped

    def tail_hash(self) -> str:
        return self._tail_hash
