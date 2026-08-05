from simulation.core.reducer import Reducer
from simulation.core.state import State
from simulation.core.event import Event

from simulation.persistence.snapshot_manager import SnapshotManager
from simulation.replay.replay_engine import ReplayEngine


class Kernel:

    def __init__(self, event_store):

        self.reducer = Reducer()

        self.event_store = event_store

        self.snapshot_manager = SnapshotManager()

        self.events = self.event_store.read_all()

        if self.events:

            replay = ReplayEngine(
                event_store=self.event_store,
                reducer=self.reducer
            )

            self.state = replay.replay()

            print(
                f"Recovered {len(self.events)} events."
            )

        else:

            self.state = State()

    def dispatch(self, event):

        sequence = len(self.events) + 1

        stored_event = Event(

            event_type=event.event_type,

            payload=event.payload,

            sequence=sequence,

            event_id=event.event_id

        )

        self.state = self.reducer.apply(
            self.state,
            stored_event
        )

        self.event_store.append(
            stored_event
        )

        self.events.append(
            stored_event
        )

        self.snapshot_manager.event_applied()

        if self.snapshot_manager.should_snapshot():

            self.snapshot_manager.save_snapshot(
                self.state
            )

    def event_count(self):

        return len(self.events)

    def get_state(self):

        return self.state