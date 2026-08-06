from simulation.core.event import Event


class MemoryEvents:

    @staticmethod
    def stored(
        key,
        value
    ):

        return Event(

            event_type="MemoryStored",

            payload={

                "key": key,

                "value": value

            }

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