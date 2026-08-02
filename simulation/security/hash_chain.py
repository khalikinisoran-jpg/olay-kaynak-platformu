import hashlib
import json


class HashChain:


    @staticmethod
    def calculate(data: dict) -> str:

        raw = json.dumps(
            data,
            sort_keys=True
        ).encode()

        return hashlib.sha256(raw).hexdigest()



    @staticmethod
    def envelope(event, previous_hash=None):

        body = {

            "event_id": event.event_id,

            "event_type": event.event_type,

            "payload": event.payload,

            "sequence": event.sequence,

            "previous_hash": previous_hash
        }


        body["current_hash"] = HashChain.calculate(body)


        return body