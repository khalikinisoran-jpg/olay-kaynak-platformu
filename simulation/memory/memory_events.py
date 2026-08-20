from simulation.core.event import Event
from simulation.memory.provenance import (
    TrustLevel,
    VerificationStatus,
)


class MemoryEvents:

    @staticmethod
    def stored(
        key,
        value,
        source=None,
        source_type=None,
        timestamp="",
        trust_level=TrustLevel.UNTRUSTED,
        verification_status=VerificationStatus.UNVERIFIED,
        run_id="",
        agent_id=""
    ):

        payload = {
            "key": key,
            "value": value,
        }

        if source is not None:

            payload["source"] = source

        if source_type is not None:

            payload["source_type"] = source_type

        if timestamp:

            payload["timestamp"] = timestamp

        payload["trust_level"] = trust_level

        payload["verification_status"] = verification_status

        if run_id:

            payload["run_id"] = run_id

        if agent_id:

            payload["agent_id"] = agent_id

        return Event(

            event_type="MemoryStored",

            payload=payload

        )

    @staticmethod
    def deleted(
        key
    ):

        return Event(

            event_type="MemoryDeleted",

            payload={

                "key": key

            }

        )