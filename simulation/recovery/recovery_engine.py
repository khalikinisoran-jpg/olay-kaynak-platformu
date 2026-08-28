import json

from simulation.core.state import State
from simulation.replay.replay_engine import ReplayEngine
from simulation.security.hash_verifier import HashVerifier


class RecoveryEngine:

    """Deterministic recovery: verify the event chain, then rebuild
    state from a verified snapshot plus the remaining events.

    Snapshot trust policy (integrity-checked load):

    - A snapshot is accepted only when it carries a ``content_hash``
      that is a 64-character hex digest and the hash recomputed from
      the snapshot's ``state`` matches it exactly.
    - A snapshot missing ``content_hash`` (legacy format), with a
      tampered ``state`` or ``content_hash``, or otherwise malformed is
      never trusted; recovery falls back to a full replay from the
      (chain-verified) event log. An unparseable snapshot file is
      treated the same way (safe fallback, never a crash mid-load).
    - The snapshot's ``last_sequence`` must be consistent with the
      event store: a snapshot that claims more events than exist in
      the verified store is rejected.
    - Event-chain corruption still raises ``RuntimeError`` (fail-closed;
      state cannot be rebuilt from unverifiable events).
    """

    def __init__(
        self,
        event_store,
        snapshot_store,
        reducer
    ):

        self.event_store = event_store
        self.snapshot_store = snapshot_store
        self.reducer = reducer

    def recover(self):

        print()
        print("===================================")
        print(" RECOVERY ENGINE")
        print("===================================")

        raw_events = self.event_store.path.read_text(
            encoding="utf-8"
        ).splitlines()

        parsed_events = []

        for line in raw_events:

            if not line.strip():

                continue

            parsed_events.append(
                json.loads(line)
            )

        verifier = HashVerifier()

        print()
        print("Integrity Check...")

        if not verifier.verify(parsed_events):

            raise RuntimeError(
                "Event chain integrity verification failed."
            )

        print("Integrity OK")

        # MISSION-N: when the event store carries an external keyed
        # trust anchor, the recomputed chain head must match the
        # anchored head exactly. This makes tail deletion / tail edit /
        # hash-recomputed middle deletion and anchor rollback fail
        # closed, which the unkeyed SHA-256 chain alone cannot do.
        anchor = getattr(
            self.event_store,
            "chain_anchor",
            None,
        )

        if anchor is not None:

            tail_sequence = (
                parsed_events[-1]["sequence"]
                if parsed_events
                else 0
            )

            tail_hash = (
                parsed_events[-1].get(
                    "current_hash",
                    parsed_events[-1].get("hash"),
                )
                if parsed_events
                else "GENESIS"
            )

            print()
            print("Trust Anchor Check...")

            if not anchor.verify(
                tail_sequence,
                tail_hash,
            ):

                raise RuntimeError(
                    "Event chain trust anchor verification failed: "
                    "the anchored chain head does not match the "
                    "event tail."
                )

            print("Trust Anchor OK")

        try:

            snapshot = self.snapshot_store.load()

        except (OSError, ValueError):

            print(
                "Snapshot file could not be read or parsed; "
                "ignoring it."
            )

            snapshot = None

        replay = ReplayEngine(
            reducer=self.reducer
        )

        if snapshot is None:

            print("No snapshot found.")

            return self._replay_all(replay)

        if not self._snapshot_is_usable(snapshot):

            print(
                "Snapshot is unverifiable or inconsistent; "
                "falling back to a full replay from the "
                "verified event log."
            )

            return self._replay_all(replay)

        print("Snapshot found.")

        print(
            f"Snapshot Version : {snapshot.get('version')}"
        )

        print(
            f"Last Sequence    : {snapshot.get('last_sequence')}"
        )

        print(
            f"Created At       : {snapshot.get('created_at')}"
        )

        state = State.from_dict(
            snapshot.get("state")
        )

        last_sequence = snapshot.get(
            "last_sequence",
            0
        )

        events = self.event_store.read_after(
            last_sequence
        )

        print(
            f"Remaining Events : {len(events)}"
        )

        state = replay.replay(
            events=events,
            initial_state=state
        )

        print("Recovery completed.")
        print("===================================")

        return state

    def _replay_all(self, replay):

        events = self.event_store.read_all()

        state = replay.replay(
            events=events
        )

        print("Recovery completed.")
        print("===================================")

        return state

    def _snapshot_is_usable(self, snapshot):

        if not isinstance(snapshot, dict):

            return False

        if "state" not in snapshot:

            return False

        if not isinstance(
            snapshot["state"],
            dict,
        ):

            return False

        content_hash = snapshot.get(
            "content_hash"
        )

        if (
            not isinstance(content_hash, str)
            or len(content_hash) != 64
            or any(
                character
                not in "0123456789abcdefABCDEF"
                for character in content_hash
            )
        ):

            return False

        computed = self._content_hash(
            snapshot["state"]
        )

        if computed != content_hash:

            return False

        last_sequence = snapshot.get(
            "last_sequence",
            0
        )

        if not isinstance(
            last_sequence,
            int,
        ) or isinstance(
            last_sequence,
            bool,
        ) or last_sequence < 0:

            return False

        event_count = len(
            self.event_store.read_all()
        )

        if last_sequence > event_count:

            return False

        return True

    @staticmethod
    def _content_hash(state_data):

        import hashlib

        return hashlib.sha256(
            json.dumps(
                state_data,
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
