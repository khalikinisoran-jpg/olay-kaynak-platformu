import json
import os
import threading

from pathlib import Path

from simulation.core.event import Event
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
    many writers share one store instance.

    Appends are serialized with an internal lock so multiple threads
    sharing one store instance cannot interleave
    ``tail_hash``/``append`` and corrupt the chain. ``append`` returns
    the authoritative sequence actually persisted so callers can keep
    their in-memory copies consistent with the log.
    """

    def __init__(
        self,
        path="data/events.jsonl"
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

        self._tail_record = self._read_tail()

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

        return sequence

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
