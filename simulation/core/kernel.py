from simulation.core.reducer import Reducer
from simulation.core.state import State
from simulation.persistence.snapshot_manager import SnapshotManager


class Kernel:

    def __init__(
        self,
        event_store
    ):

        self.reducer = Reducer()

        self.state = State(
            tasks={},
            workers={},
            event_counter=0
        )

        self.event_store = event_store

        self.snapshot_manager = SnapshotManager()

        self.events = []


    def dispatch(self, event):

        self.state = self.reducer.apply(
            self.state,
            event
        )


        self.event_store.append(
            event
        )


        self.events.append(
            event
        )


        self.snapshot_manager.event_applied()


        if self.snapshot_manager.should_snapshot():

            self.snapshot_manager.save_snapshot(
                self.state
            )



    def event_count(self):

        return len(
            self.events
        )



    def get_state(self):

        return self.state