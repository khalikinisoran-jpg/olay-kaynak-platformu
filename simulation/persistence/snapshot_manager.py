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

        # P6.1: Windows cp1252 compatibility — avoid '\u0131' (dotless i) which fails on hosted Windows
        try:
            print(
                f"Otomatik snapshot alindi. "
                f"Event sayisi: {last_sequence}"
            )
        except UnicodeEncodeError:
            # Fallback: write via buffer with replacement
            import sys
            sys.stdout.buffer.write(
                f"Otomatik snapshot alindi. Event sayisi: {last_sequence}\n".encode("utf-8", errors="replace")
            )
            sys.stdout.buffer.flush()