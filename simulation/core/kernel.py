from simulation.core.reducer import Reducer
from simulation.core.event import Event

from simulation.persistence.snapshot_manager import SnapshotManager
from simulation.recovery.recovery_engine import RecoveryEngine

from simulation.decision.decision_trace import DecisionTrace


class Kernel:

    def __init__(self, event_store, snapshot_manager=None):

        self.reducer = Reducer()

        self.event_store = event_store

        self.snapshot_manager = (
            snapshot_manager
            if snapshot_manager is not None
            else SnapshotManager()
        )

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

        """Persist and apply one event (the single write path).

        Ordering contract (MISSION-019, documented semantics):

        1. ``append`` — the event is durably persisted (fsynced) and
           the store assigns the authoritative sequence.
        2. ``trace`` — the decision trace records the dispatch.
        3. ``reducer`` — the in-memory state is projected forward.

        If the reducer raises for a persisted event (a malformed
        payload for a reducer-handled event type), the exception
        propagates and the live state is NOT updated for that event:
        the event remains durably in the store while ``self.events``
        and the live state diverge from it. On restart, recovery
        re-applies the event from the (chain-verified) store and
        therefore reproduces the same reducer failure — fail-closed,
        with no silent state divergence. The event store is the
        authority; the reducer must be total for every event the store
        can contain.
        """

        sequence = self.event_store.append(event)

        stored_event = Event(
            event_type=event.event_type,
            payload=event.payload,
            sequence=sequence,
            event_id=event.event_id
        )

        self.decision_trace.record(
            stage="Dispatch",
            message=stored_event.event_type,
            metadata={
                "sequence": sequence
            }
        )

        self.state = self.reducer.apply(
            self.state,
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