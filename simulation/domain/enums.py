from enum import Enum


class TaskStatus(str, Enum):
    CREATED = "CREATED"
    WAITING = "WAITING"
    ASSIGNED = "ASSIGNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class WorkerStatus(str, Enum):
    ONLINE = "ONLINE"
    BUSY = "BUSY"
    DEAD = "DEAD"