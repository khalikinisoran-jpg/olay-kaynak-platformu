from simulation.core.state import State
from simulation.replay.replay_engine import ReplayEngine


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

        events = self.event_store.read_all()

        state = replay.replay(
            events=events
        )

        print("Recovery completed.")
        print("===================================")

        return state