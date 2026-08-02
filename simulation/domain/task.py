from dataclasses import dataclass
from simulation.domain.enums import TaskStatus


@dataclass(frozen=True)
class Task:

    task_id: str
    name: str
    status: TaskStatus = TaskStatus.CREATED
    assigned_worker: str | None = None
    retry_count: int = 0
    version: int = 0