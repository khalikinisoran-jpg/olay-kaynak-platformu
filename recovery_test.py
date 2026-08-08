from simulation.persistence.event_store import EventStore
from simulation.persistence.snapshot import SnapshotStore

from simulation.core.reducer import Reducer
from simulation.recovery.recovery_engine import RecoveryEngine


def test_recovery_uses_isolated_storage(
    isolated_event_store,
    isolated_snapshot_store
):

    reducer = Reducer()

    recovery = RecoveryEngine(
        event_store=isolated_event_store,
        snapshot_store=isolated_snapshot_store,
        reducer=reducer
    )

    state = recovery.recover()

    assert state is not None