from dataclasses import dataclass
from simulation.domain.enums import WorkerStatus


@dataclass
class Worker:
    worker_id: str
    status: WorkerStatus = WorkerStatus.ONLINE

    def mark_dead(self):
        self.status = WorkerStatus.DEAD

    def is_alive(self):
        return self.status != WorkerStatus.DEAD