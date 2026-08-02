from simulation.persistence.snapshot import SnapshotStore


class SnapshotManager:

    def __init__(
        self,
        interval=10
    ):

        self.interval = interval
        self.counter = 0
        self.snapshot_store = SnapshotStore()


    def should_snapshot(self):

        return self.counter > 0 and self.counter % self.interval == 0


    def event_applied(self):

        self.counter += 1


    def save_snapshot(self, state):

        self.snapshot_store.save(
            state
        )

        print(
            "Otomatik snapshot alındı. Event sayısı:",
            self.counter
        )