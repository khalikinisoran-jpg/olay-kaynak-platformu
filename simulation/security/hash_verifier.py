import json
import hashlib


class HashVerifier:

    def calculate(self, data):

        raw = json.dumps(
            data,
            sort_keys=True
        ).encode()

        return hashlib.sha256(raw).hexdigest()


    def verify(self, events):

        previous_hash = "GENESIS"


        for event in events:

            body = {

                "event_id": event["event_id"],

                "event_type": event["event_type"],

                "payload": event["payload"],

                "sequence": event["sequence"],

                "previous_hash": previous_hash
            }


            calculated = self.calculate(body)


            stored = event.get(
                "current_hash",
                event.get("hash")
            )


            if calculated != stored:

                print("Hash bozuk:")
                print(event["event_id"])

                return False


            previous_hash = stored


        return True