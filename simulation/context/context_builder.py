class ContextBuilder:

    def build(
        self,
        kernel
    ) -> str:

        state = kernel.get_state()

        lines = []

        lines.append(
            "=== CURRENT STATE ==="
        )

        lines.append(
            f"Tasks: {len(state.tasks)}"
        )

        lines.append(
            f"Workers: {len(state.workers)}"
        )

        lines.append(
            f"Events: {state.event_counter}"
        )

        if state.tasks:

            lines.append("")
            lines.append("Task List:")

            for task in state.tasks.values():

                lines.append(
                    f"- {task.task_id}: {task.name}"
                )

        return "\n".join(lines)