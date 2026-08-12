import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone


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

    def save(
        self,
        state,
        last_sequence=None
    ):

        if hasattr(state, "to_dict"):

            state_data = state.to_dict()

        else:

            state_data = state

        content_hash = hashlib.sha256(
            json.dumps(
                state_data,
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()

        snapshot = {

            "version": 2,

            "last_sequence": last_sequence,

            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),

            "content_hash": content_hash,

            "state": state_data

        }

        with open(
            self.path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                snapshot,
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
