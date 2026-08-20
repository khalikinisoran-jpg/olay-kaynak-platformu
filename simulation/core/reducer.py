from dataclasses import replace

from simulation.core.state import State
from simulation.domain.task import Task
from simulation.memory.provenance import MemoryProvenance


class Reducer:

    def apply(
        self,
        state: State,
        event
    ):

        tasks = dict(state.tasks)

        workers = dict(state.workers)

        memory = dict(state.memory)

        memory_provenance = dict(state.memory_provenance)

        conversation_history = list(
            state.conversation_history
        )

        worker_trace = list(
            state.worker_trace
        )

        if event.event_type == "TaskCreated":

            task = Task(
                task_id=event.payload["task_id"],
                name=event.payload["name"]
            )

            tasks[task.task_id] = task

        elif event.event_type == "UserQuestionReceived":

            conversation_history.append({

                "role": "user",

                "content": event.payload["prompt"]

            })

        elif event.event_type == "AIResponseReceived":

            conversation_history.append({

                "role": "assistant",

                "content": event.payload["response"]

            })

            print(
                "\nReducer -> AI Event işlendi."
            )

        elif event.event_type == "MemoryStored":

            payload = event.payload

            if not isinstance(payload, dict):

                raise ValueError(
                    "MemoryStored payload must be an object."
                )

            key = payload.get("key")

            value = payload.get("value")

            if not isinstance(key, str) or not key:

                raise ValueError(
                    "MemoryStored requires a non-empty "
                    "string key."
                )

            if not isinstance(value, str):

                raise ValueError(
                    "MemoryStored value must be a string."
                )

            memory[key] = value

            # MISSION-N: every memory write carries a deterministic
            # provenance envelope derived from the event payload. The
            # envelope is METADATA only and is never consulted by any
            # governance/approval/risk/scope/apply decision.
            memory_provenance[key] = (
                MemoryProvenance.from_payload(
                    payload,
                    event_id=event.event_id,
                )
            )

            print(
                f"\nReducer -> Memory kaydedildi: "
                f"{key}"
            )

        elif event.event_type == "MemoryDeleted":

            payload = event.payload

            if not isinstance(payload, dict):

                raise ValueError(
                    "MemoryDeleted payload must be an object."
                )

            key = payload.get("key")

            if not isinstance(key, str) or not key:

                raise ValueError(
                    "MemoryDeleted requires a non-empty "
                    "string key."
                )

            memory.pop(key, None)

            memory_provenance.pop(key, None)

            print(
                f"\nReducer -> Memory silindi: {key}"
            )

        elif event.event_type.startswith("Worker"):

            worker_trace.append({

                "event_type": event.event_type,

                "sequence": event.sequence,

                "payload": event.payload

            })

        return State(

            tasks=tasks,

            workers=workers,

            memory=memory,

            memory_provenance=memory_provenance,

            conversation_history=conversation_history,

            worker_trace=worker_trace,

            event_counter=state.event_counter + 1

        )