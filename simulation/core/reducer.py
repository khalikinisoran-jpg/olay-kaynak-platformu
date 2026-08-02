from simulation.core.state import State
from simulation.domain.task import Task
from simulation.domain.enums import TaskStatus


class Reducer:

    def apply(self, state: State, event):

        if event.event_type == "TaskCreated":

            task = Task(
                task_id=event.payload["task_id"],
                name=event.payload["name"]
            )

            state.tasks[task.task_id] = task

        return State(
            tasks=state.tasks,
            workers=state.workers,
            event_counter=state.event_counter + 1
        )