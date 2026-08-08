from simulation.persistence.snapshot import SnapshotStore


class SnapshotManager:

    def __init__(
        self,
        interval=2,
        snapshot_store=None
    ):

        self.interval = interval
        self.counter = 0

        self.snapshot_store = (
            snapshot_store
            if snapshot_store is not None
            else SnapshotStore()
        )

    def should_snapshot(self):

        return (
            self.counter > 0
            and self.counter % self.interval == 0
        )

    def event_applied(self):

        self.counter += 1

    def save_snapshot(
        self,
        state,
        last_sequence=None
    ):

        self.snapshot_store.save(
            state=state,
            last_sequence=last_sequence
        )

        print(
            f"Otomatik snapshot alındı. "
            f"Event sayısı: {last_sequence}"
        )