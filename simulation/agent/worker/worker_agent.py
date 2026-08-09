from pathlib import Path

from simulation.agent.worker.patch_generator import PatchGenerator
from simulation.agent.worker.worker_policy import WorkerPolicy
from simulation.agent.worker.worker_result import WorkerResult
from simulation.agent.worker.worker_task import WorkerTask


class WorkerAgent:

    def __init__(self):

        self.policy = WorkerPolicy()

        self.patch_generator = PatchGenerator()

    def run(
        self,
        task: WorkerTask
    ) -> WorkerResult:

        if not self.policy.allows("read"):

            return WorkerResult(
                task_id=task.task_id,
                success=False,
                summary="Worker policy denied read action."
            )

        if not self.policy.allows("inspect"):

            return WorkerResult(
                task_id=task.task_id,
                success=False,
                summary="Worker policy denied inspect action."
            )

        if not self.policy.allows("propose"):

            return WorkerResult(
                task_id=task.task_id,
                success=False,
                summary="Worker policy denied propose action."
            )

        if not task.allowed_paths:

            return WorkerResult(
                task_id=task.task_id,
                success=False,
                summary="No allowed paths were provided."
            )

        evidence = []
        proposals = []
        patches = []

        for path_value in task.allowed_paths:

            path = Path(path_value)

            if not path.exists():

                evidence.append({
                    "path": path_value,
                    "action": "read",
                    "status": "not_found"
                })

                continue

            if not path.is_file():

                evidence.append({
                    "path": path_value,
                    "action": "read",
                    "status": "not_a_file"
                })

                continue

            try:

                content = path.read_text(
                    encoding="utf-8"
                )

                evidence.append({
                    "path": path_value,
                    "action": "read",
                    "status": "success",
                    "characters": len(content)
                })

                patch = self.patch_generator.generate(
                    path=path_value,
                    old_content=content,
                    description=task.description,
                    allowed_paths=task.allowed_paths
                )

                patches.append(patch)

                proposals.append(
                    f"Patch proposal generated for "
                    f"{path_value}."
                )

            except Exception as exc:

                evidence.append({
                    "path": path_value,
                    "action": "read",
                    "status": "failed",
                    "error": str(exc)
                })

        proposal_text = (
            "\n".join(proposals)
            if proposals
            else None
        )

        return WorkerResult(
            task_id=task.task_id,
            success=True,
            summary=(
                "Worker inspection and patch proposal completed."
            ),
            evidence=tuple(evidence),
            proposal=proposal_text,
            patches=tuple(patches)
        )