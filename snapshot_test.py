import tempfile

from simulation.persistence.snapshot import SnapshotStore
from simulation.persistence.snapshot_manager import SnapshotManager
from simulation.core.state import State


with tempfile.TemporaryDirectory() as temp_dir:

    snapshot_path = f"{temp_dir}/snapshot.json"

    snapshot_store = SnapshotStore(
        path=snapshot_path
    )

    manager = SnapshotManager(
        snapshot_store=snapshot_store
    )

    state = State()

    manager.save_snapshot(
        state=state,
        last_sequence=0
    )

    snapshot = snapshot_store.load()


    print()

    print("===================================")
    print(" SNAPSHOT TEST")
    print("===================================")

    print(snapshot)

    print("===================================")