from dataclasses import dataclass, field
from typing import Dict, Any, List


@dataclass(frozen=True)
class State:

    tasks: Dict[str, Any] = field(
        default_factory=dict
    )

    workers: Dict[str, Any] = field(
        default_factory=dict
    )

    conversation_history: List[dict] = field(
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

        return {

            "event_counter": self.event_counter,

            "tasks": tasks,

            "workers": workers,

            "conversation_history": self.conversation_history

        }