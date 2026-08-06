from simulation.core.state import State
from simulation.replay.replay_engine import ReplayEngine
from simulation.security.hash_verifier import HashVerifier


class RecoveryEngine:

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

        import json

        for line in raw_events:

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

        snapshot = self.snapshot_store.load()

        replay = ReplayEngine(
            reducer=self.reducer
        )

        if snapshot is None:

            print("No snapshot found.")

            events = self.event_store.read_all()

            state = replay.replay(
                events=events
            )

            print("Recovery completed.")
            print("===================================")

            return state

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