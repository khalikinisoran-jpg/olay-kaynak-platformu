from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WorkerTask:

    task_id: str
    description: str
    allowed_paths: tuple[str, ...] = ()
    read_paths: tuple[str, ...] = ()
    allowed_actions: tuple[str, ...] = ()
    expected_output: str = ""
    attempt: int | None = None
    recovery_evidence: tuple[Any, ...] = ()