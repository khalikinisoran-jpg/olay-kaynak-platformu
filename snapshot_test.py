from simulation.persistence.snapshot import SnapshotStore


snapshot = SnapshotStore()

snapshot.save(
    {
        "event_counter": 1,
        "tasks": {
            "T001": {
                "name": "Disk Test"
            }
        }
    }
)

print("Snapshot kaydedildi.")

print(snapshot.load())