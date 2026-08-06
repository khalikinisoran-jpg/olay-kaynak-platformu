from simulation.core.reducer import Reducer
from simulation.core.event import Event

from simulation.persistence.snapshot_manager import SnapshotManager
from simulation.recovery.recovery_engine import RecoveryEngine
from simulation.decision.decision_trace import DecisionTrace


class Kernel:

    def __init__(self, event_store):

        self.reducer = Reducer()

        self.event_store = event_store

        self.snapshot_manager = SnapshotManager()

        self.decision_trace = DecisionTrace()

        recovery = RecoveryEngine(
            event_store=self.event_store,
            snapshot_store=self.snapshot_manager.snapshot_store,
            reducer=self.reducer
        )

        self.state = recovery.recover()

        self.events = self.event_store.read_all()

        print(
            f"Recovered {len(self.events)} events."
        )

    def dispatch(self, event):

        sequence = len(self.events) + 1

        self.decision_trace.record(
            stage="Dispatch",
            message=event.event_type,
            metadata={
                "sequence": sequence
            }
        )

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
                state=self.state,
                last_sequence=len(self.events)
            )

    def event_count(self):

        return len(self.events)

    def get_state(self):

        return self.state

    def get_decision_trace(self):

        return self.decision_trace