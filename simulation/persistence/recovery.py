from simulation.core.state import State
from simulation.core.reducer import Reducer
from simulation.core.event import Event

from simulation.persistence.snapshot import SnapshotStore


class Recovery:

    def __init__(self, event_store):

        self.event_store = event_store
        self.reducer = Reducer()

        self.snapshot = SnapshotStore()


    def rebuild(self):

        snapshot = self.snapshot.load()

        if snapshot is not None:

            print("Snapshot bulundu.")
            print(snapshot)

        else:

            print("Snapshot bulunamadı.")
            print("Event'lerden yeniden oluşturuluyor...")

        state = State(
            tasks={},
            workers={},
            event_counter=0
        )

        records = self.event_store.read_all()

        for r in records:

            event = Event(
                event_id=r["event_id"],
                event_type=r["event_type"],
                payload=r["payload"],
                sequence=r["sequence"]
            )

            state = self.reducer.apply(
                state,
                event
            )

        return state