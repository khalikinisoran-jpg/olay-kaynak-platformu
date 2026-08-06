from simulation.persistence.event_store import EventStore
from simulation.persistence.snapshot import SnapshotStore

from simulation.core.reducer import Reducer

from simulation.recovery.recovery_engine import RecoveryEngine


event_store = EventStore()

snapshot_store = SnapshotStore()

reducer = Reducer()


recovery = RecoveryEngine(

    event_store=event_store,

    snapshot_store=snapshot_store,

    reducer=reducer

)


state = recovery.recover()


print()

print("===================================")
print(" RECOVERY TEST")
print("===================================")

print(state)

print("===================================")