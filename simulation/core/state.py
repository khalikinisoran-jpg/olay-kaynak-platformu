from dataclasses import dataclass, field
from typing import Dict, Any, List

from simulation.memory.provenance import MemoryProvenance


@dataclass(frozen=True)
class State:

    tasks: Dict[str, Any] = field(
        default_factory=dict
    )

    workers: Dict[str, Any] = field(
        default_factory=dict
    )

    memory: Dict[str, Any] = field(
        default_factory=dict
    )

    # MISSION-N: parallel origin metadata for ``memory`` keys. Each
    # entry is a ``MemoryProvenance`` dict. This is METADATA only and
    # is never consulted by governance / approval / scope / risk /
    # apply.
    memory_provenance: Dict[str, Any] = field(
        default_factory=dict
    )

    conversation_history: List[dict] = field(
        default_factory=list
    )

    worker_trace: List[Any] = field(
        default_factory=list
    )

    event_counter: int = 0

    def to_dict(self):

        tasks = {}

        for key, value in self.tasks.items():

            if hasattr(value, "__dict__"):

                tasks[key] = value.__dict__

            else:

                tasks[key] = value

        workers = {}

        for key, value in self.workers.items():

            if hasattr(value, "__dict__"):

                workers[key] = value.__dict__

            else:

                workers[key] = value

        provenance = {}

        for key, record in self.memory_provenance.items():

            if isinstance(record, MemoryProvenance):

                provenance[key] = record.to_dict()

            elif hasattr(record, "to_dict"):

                provenance[key] = record.to_dict()

            elif isinstance(record, dict):

                provenance[key] = record

        return {

            "event_counter": self.event_counter,

            "tasks": tasks,

            "workers": workers,

            "memory": self.memory,

            "memory_provenance": provenance,

            "conversation_history": self.conversation_history,

            "worker_trace": self.worker_trace

        }

    @classmethod
    def from_dict(
        cls,
        data
    ):

        if data is None:

            return cls()

        return cls(

            event_counter=data.get(
                "event_counter",
                0
            ),

            tasks=data.get(
                "tasks",
                {}
            ),

            workers=data.get(
                "workers",
                {}
            ),

            memory=data.get(
                "memory",
                {}
            ),

            memory_provenance=cls._restore_provenance(
                data.get(
                    "memory_provenance",
                    {}
                )
            ),

            conversation_history=data.get(
                "conversation_history",
                []
            ),

            worker_trace=data.get(
                "worker_trace",
                []
            )

        )

    @staticmethod
    def _restore_provenance(data):

        """Rebuild provenance envelopes from a serialized snapshot.

        Keeps live-state type consistency (``MemoryProvenance`` objects
        everywhere) while tolerating legacy snapshots that lack the
        field entirely or carry raw dicts.
        """

        if not isinstance(data, dict):

            return {}

        restored = {}

        for key, record in data.items():

            if isinstance(record, MemoryProvenance):

                restored[key] = record

            elif isinstance(record, dict):

                restored[key] = MemoryProvenance.from_dict(record)

            else:

                restored[key] = MemoryProvenance()

        return restored