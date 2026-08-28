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

        for index, event in enumerate(events):

            # MISSION-M: sequence-contiguity enforcement. The event
            # store allocates strictly contiguous sequences starting at
            # 1, so a valid stream must satisfy ``sequence ==
            # position + 1``. This catches (a) a sequence jump, (b) a
            # hash-recomputed middle deletion (the gap survives even
            # when every current_hash is rewritten), and (c) a
            # duplicated sequence. A gap is fail-closed: the chain can
            # never be accepted with a missing position.
            expected_sequence = index + 1

            if event.get("sequence") != expected_sequence:

                return False

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