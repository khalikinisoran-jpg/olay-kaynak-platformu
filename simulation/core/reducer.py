from simulation.core.state import State
from simulation.domain.task import Task


class Reducer:

    def apply(self, state: State, event):

        tasks = dict(state.tasks)
        workers = dict(state.workers)

        if event.event_type == "TaskCreated":

            task = Task(
                task_id=event.payload["task_id"],
                name=event.payload["name"]
            )

            tasks[task.task_id] = task


        elif event.event_type == "AIResponseReceived":

            print("\nReducer -> AI Event işlendi.")


        return State(
            tasks=tasks,
            workers=workers,
            event_counter=state.event_counter + 1
        )