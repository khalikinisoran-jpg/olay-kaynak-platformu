import json
from pathlib import Path

from simulation.core.event import Event
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

        self.path.touch(
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

                record = json.loads(line)

                event = Event(

                    event_type=record["event_type"],

                    payload=record["payload"],

                    sequence=record.get(
                        "sequence",
                        0
                    ),

                    event_id=record.get(
                        "event_id"
                    )

                )

                events.append(
                    event
                )

        return events

    def read_after(
        self,
        sequence
    ):

        events = self.read_all()

        return [

            event

            for event in events

            if event.sequence > sequence

        ]

    def last_hash(self):

        if not self.path.exists():

            return "GENESIS"

        last_record = None

        with open(
            self.path,
            "r",
            encoding="utf-8"
        ) as f:

            for line in f:

                last_record = json.loads(
                    line
                )

        if last_record is None:

            return "GENESIS"

        return last_record.get(
            "current_hash",
            "GENESIS"
        )