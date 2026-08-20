import json
import os
import threading

from pathlib import Path

from simulation.core.event import Event
from simulation.persistence.chain_anchor import (
    ChainAnchor,
    ChainAnchorError,
)
from simulation.persistence.process_lock import (
    EventStoreBusyError,
    _ProcessFileLock,
)
from simulation.security.hash_chain import HashChain


class EventStore:

    """Append-only, hash-chained event store.

    Every record carries ``previous_hash`` / ``current_hash`` (SHA-256
    over the serialized record). The store keeps the last record's
    sequence and hash in memory after an initial one-time scan, so
    ``append`` is O(1) instead of re-reading the whole file.

    The store is the *sole* authority for sequence allocation: ``append``
    assigns the next sequence from its own tail, inside its internal
    lock, and any caller-supplied ``event.sequence`` is ignored for
    allocation. This guarantees strictly unique, monotonically
    increasing, contiguous sequences and a valid hash chain even when
    many threads share one store instance.

    MISSION-N trust anchor (optional): when ``anchor_path`` is provided,
    every append also updates an external keyed ``ChainAnchor``. The
    anchor makes tail deletion / tail edit / hash-recomputed middle
    deletion detectable by recovery (FAIL CLOSED). With no anchor the
    store behaves exactly as before (legacy unanchored mode).

    MISSION-O single-writer enforcement: the append critical section
    (read tail -> allocate -> write record -> update anchor) and the
    construction tail-read are guarded by an OS-level advisory file
    lock (``_ProcessFileLock``). A second OS process writing the same
    store either waits briefly and then succeeds (serialized) or fails
    closed with ``EventStoreBusyError`` when the holder does not
    release within the timeout. The lock is released automatically by
    the OS if the holder crashes (no stale lock, no permanent
    deadlock). Cross-process single-writer is therefore enforced among
    cooperating ``EventStore`` instances.
    """

    def __init__(
        self,
        path="data/events.jsonl",
        anchor_path=None,
        anchor_key=None,
        anchor_key_path=None,
        writer_lock_timeout=_ProcessFileLock.DEFAULT_TIMEOUT
    ):

        self.path = Path(path)

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        self.path.touch(
            exist_ok=True
        )

        self._lock = threading.Lock()

        self._process_lock = _ProcessFileLock(
            self.path,
            timeout=writer_lock_timeout,
        )

        self.chain_anchor = None

        with self._process_lock:

            self._tail_record = self._read_tail()

            self._file_size = self._snapshot_file_size()

            if anchor_path is not None:

                try:

                    self.chain_anchor = ChainAnchor(
                        path=anchor_path,
                        anchor_key=anchor_key,
                        anchor_key_path=anchor_key_path,
                    )

                except ChainAnchorError:

                    raise

    def _snapshot_file_size(self):

        try:

            return os.path.getsize(self.path)

        except OSError:

            return 0

    def _sync_if_stale(self):

        """Re-read the file tail when another writer grew the log.

        Called UNDER the process lock, so the check-and-resync is atomic
        with respect to every cooperating ``EventStore`` writer. In the
        single-writer case the size never changes externally and this is
        a single ``getsize`` no-op (O(1) fast path). When a second
        writer appended, the cached tail is stale and the sequence /
        previous_hash derived from it would collide, so it is re-read
        from the file before allocation.
        """

        current_size = self._snapshot_file_size()

        if current_size == self._file_size:

            return

        self._tail_record = self._read_tail()

        self._file_size = current_size

    def _read_tail(self):

        """Return the last parsed record, or None for an empty store."""

        last_record = None

        with open(
            self.path,
            "r",
            encoding="utf-8"
        ) as f:

            for line in f:

                if not line.strip():

                    continue

                last_record = json.loads(line)

        return last_record

    def append(self, event):

        with self._lock:

            with self._process_lock:

                self._sync_if_stale()

                previous_hash = self.tail_hash()

                sequence = self.next_sequence()

                record = {

                    "event_id": event.event_id,

                    "event_type": event.event_type,

                    "payload": event.payload,

                    "sequence": sequence,

                    "previous_hash": previous_hash

                }

                record["current_hash"] = HashChain.calculate(
                    record
                )

                self._write_record(record)

                self._tail_record = record

                self._file_size = self._snapshot_file_size()

                if self.chain_anchor is not None:

                    # MISSION-N: the anchor is updated AFTER the event
                    # record is durably fsynced. A crash between the two
                    # leaves events beyond the anchored head, which the next
                    # recovery rejects (FAIL CLOSED) instead of silently
                    # trusting a partially-anchored tail.
                    self.chain_anchor.anchor(
                        sequence,
                        record["current_hash"],
                    )

        return sequence

    def verify_tail_anchor(self):

        """Verify the anchored chain head against the current tail.

        Returns True when no anchor is configured (legacy unanchored
        mode) or when the anchor matches the tail read from the file
        right now. The on-disk tail is re-read instead of trusting the
        in-memory cache so an external mutation after construction is
        detected (TOCTOU robustness). Raises ``ChainAnchorError`` on
        mismatch so callers fail closed instead of silently trusting a
        truncated or edited history.
        """

        if self.chain_anchor is None:

            return True

        live_tail = self._read_tail()

        if live_tail is None:

            tail_sequence = 0

            tail_hash = "GENESIS"

        else:

            tail_sequence = live_tail.get(
                "sequence",
                0,
            )

            tail_hash = live_tail.get(
                "current_hash",
                "GENESIS",
            )

        if not self.chain_anchor.verify(
            tail_sequence,
            tail_hash,
        ):

            raise ChainAnchorError(
                "Event chain trust anchor verification failed: "
                "the anchored chain head does not match the event "
                "tail (tail deletion, edit, or anchor rollback "
                "detected)."
            )

        return True

    def _write_record(self, record):

        line = (
            json.dumps(
                record,
                ensure_ascii=False
            )
            + "\n"
        ).encode("utf-8")

        with open(
            self.path,
            "ab"
        ) as f:

            f.write(line)

            f.flush()

            os.fsync(f.fileno())

    def read_all(self):

        if not self.path.exists():

            return []

        events = []

        with open(
            self.path,
            "r",
            encoding="utf-8"
        ) as f:

            for line in f:

                if not line.strip():

                    continue

                record = json.loads(line)

                event = Event(

                    event_type=record["event_type"],

                    payload=record["payload"],

                    sequence=record.get(
                        "sequence",
                        0
                    ),

                    event_id=record.get(
                        "event_id"
                    )

                )

                events.append(
                    event
                )

        return events

    def read_after(
        self,
        sequence
    ):

        events = self.read_all()

        return [

            event

            for event in events

            if event.sequence > sequence

        ]

    def last_hash(self):

        return self.tail_hash()

    def tail_hash(self):

        if self._tail_record is None:

            return "GENESIS"

        return self._tail_record.get(
            "current_hash",
            "GENESIS"
        )

    def next_sequence(self):

        """Next sequence number based on the cached tail.

        Read-only helper kept for compatibility. Authoritative sequence
        allocation happens inside ``append`` under the store lock, so an
        externally observed ``next_sequence()`` is only a hint and can
        never override the store's own allocation.
        """

        if self._tail_record is None:

            return 1

        sequence = self._tail_record.get(
            "sequence",
            0
        )

        return sequence + 1

    def tail_sequence(self):

        if self._tail_record is None:

            return 0

        return self._tail_record.get(
            "sequence",
            0
        )
