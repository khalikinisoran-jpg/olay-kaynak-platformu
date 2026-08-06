from simulation.persistence.snapshot_manager import SnapshotManager
from simulation.core.state import State


manager = SnapshotManager()

state = State()

manager.save_snapshot(state)

snapshot = manager.snapshot_store.load()


print()

print("===================================")
print(" SNAPSHOT TEST")
print("===================================")

print(snapshot)

print("===================================")