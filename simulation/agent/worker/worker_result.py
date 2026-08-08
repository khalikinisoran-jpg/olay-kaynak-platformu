from dataclasses import dataclass, field
from typing import Any

from simulation.agent.worker.patch_proposal import PatchProposal


@dataclass(frozen=True)
class WorkerResult:

    task_id: str
    success: bool
    summary: str
    evidence: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    proposal: str | None = None
    patches: tuple[PatchProposal, ...] = field(default_factory=tuple)