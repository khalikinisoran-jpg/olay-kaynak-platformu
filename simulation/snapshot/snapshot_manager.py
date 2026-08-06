import json
from pathlib import Path


class SnapshotManager:

    def __init__(self):

        self.snapshot_path = Path(
            "data/snapshot.json"
        )

    def save(self, state):

        self.snapshot_path.parent.mkdir(
            exist_ok=True
        )

        with open(
            self.snapshot_path,
            "w",
            encoding="utf-8"
        ) as file:

            json.dump(
                state.to_dict(),
                file,
                indent=4,
                ensure_ascii=False
            )

        print(
            f"Snapshot saved -> {self.snapshot_path}"
        )

    def load(self):

        if not self.snapshot_path.exists():

            return None

        with open(
            self.snapshot_path,
            "r",
            encoding="utf-8"
        ) as file:

            snapshot = json.load(file)

        print(
            f"Snapshot loaded <- {self.snapshot_path}"
        )

        return snapshot