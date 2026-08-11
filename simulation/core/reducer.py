from dataclasses import replace

from simulation.core.state import State
from simulation.domain.task import Task


class Reducer:

    def apply(
        self,
        state: State,
        event
    ):

        tasks = dict(state.tasks)

        workers = dict(state.workers)

        memory = dict(state.memory)

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

            memory[
                event.payload["key"]
            ] = event.payload["value"]

            print(
                f"\nReducer -> Memory kaydedildi: "
                f"{event.payload['key']}"
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

            conversation_history=conversation_history,

            worker_trace=worker_trace,

            event_counter=state.event_counter + 1

        )