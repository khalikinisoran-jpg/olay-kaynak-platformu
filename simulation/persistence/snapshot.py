import json
from pathlib import Path


class SnapshotStore:

    def __init__(
        self,
        path="data/snapshot.json"
    ):

        self.path = Path(path)

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True
        )


    def save(self, state):

        if hasattr(state, "to_dict"):

            data = state.to_dict()

        else:

            data = state


        with open(
            self.path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                data,
                f,
                ensure_ascii=False,
                indent=4
            )


    def load(self):

        if not self.path.exists():

            return None


        with open(
            self.path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)