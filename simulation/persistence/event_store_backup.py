import json
from pathlib import Path


class EventStore:

    def __init__(self, path="data/events.jsonl"):
        self.path = Path(path)

        # data klasörü yoksa oluştur
        self.path.parent.mkdir(
            parents=True,
            exist_ok=True
        )


    def append(self, event):

        data = {
            "event_type": event.event_type,
            "payload": event.payload,
            "sequence": event.sequence,
            "event_id": event.event_id
        }

        with open(
            self.path,
            "a",
            encoding="utf-8"
        ) as f:

            f.write(
                json.dumps(data)
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