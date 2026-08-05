import json
from pathlib import Path

from simulation.security.hash_chain import HashChain


class EventStore:

    def __init__(
        self,
        path="data/events.jsonl"
    ):

        self.path = Path(path)

        self.path.parent.mkdir(
            parents=True,
            exist_ok=True
        )


    def append(self, event):

        previous_hash = self.last_hash()

        record = {

            "event_id": event.event_id,

            "event_type": event.event_type,

            "payload": event.payload,

            "sequence": event.sequence,

            "previous_hash": previous_hash

        }

        record["current_hash"] = HashChain.calculate(
            record
        )

        with open(
            self.path,
            "a",
            encoding="utf-8"
        ) as f:

            f.write(
                json.dumps(
                    record,
                    ensure_ascii=False
                )
                + "\n"
            )


    def read_all(self):

        if not self.path.exists():

            return []

        events = []

        with open(
            self.path,
            "r",
            encoding="utf-8"
        ) as f:

            for line in f:

                events.append(
                    json.loads(line)
                )

        return events


    def last_hash(self):

        events = self.read_all()

        if not events:

            return "GENESIS"

        return events[-1].get(
            "current_hash",
            "GENESIS"
        )