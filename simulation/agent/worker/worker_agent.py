from pathlib import Path

from simulation.agent.worker.llm_code_analyzer import (
    LLMCodeAnalyzer
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)

from simulation.agent.worker.worker_policy import (
    WorkerPolicy
)

from simulation.agent.worker.worker_result import (
    WorkerResult
)

from simulation.agent.worker.worker_task import (
    WorkerTask
)

from simulation.security.path_policy import (
    PathPolicy
)


class WorkerAgent:

    def __init__(
        self,
        analyzer=None,
        path_policy=None
    ):

        self.policy = WorkerPolicy()

        self.path_policy = (
            path_policy
            if path_policy is not None
            else PathPolicy()
        )

        self.llm_analyzer = (
            analyzer
            if analyzer is not None
            else LLMCodeAnalyzer()
        )

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
        denials = []

        read_targets = (
            task.read_paths
            if task.read_paths
            else task.allowed_paths
        )

        for path_value in read_targets:

            in_scope, scope_message = (
                self.path_policy.check_scope(
                    path_value,
                    task.allowed_paths
                )
            )

            if not in_scope:

                denials.append(
                    scope_message
                )

                evidence.append({
                    "path": path_value,
                    "action": "read",
                    "status": "denied",
                    "error": scope_message
                })

                continue

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

                (
                    diagnosis,
                    old_text,
                    new_text
                ) = self.llm_analyzer.analyze(
                    path=path_value,
                    content=content,
                    description=task.description
                )

                if content.count(old_text) != 1:

                    raise ValueError(
                        "LLM old_text must occur exactly "
                        "once in the current file."
                    )

                new_content = content.replace(
                    old_text,
                    new_text,
                    1
                )

                patch = PatchProposal(
                    path=path_value,
                    action="modify",
                    reason=diagnosis,
                    old_content=content,
                    new_content=new_content,
                    allowed_paths=task.allowed_paths
                )

                patches.append(patch)

                proposals.append(
                    diagnosis
                )

            except Exception as exc:

                evidence.append({
                    "path": path_value,
                    "action": "inspect",
                    "status": "failed",
                    "error": str(exc)
                })

        proposal_text = (
            "\n".join(proposals)
            if proposals
            else None
        )

        success = len(patches) > 0

        if denials and not patches:

            summary = (
                "Worker denied out-of-scope file reads."
            )

        elif success:

            summary = (
                "Worker inspection and patch proposal "
                "completed."
            )

        else:

            summary = (
                "Worker inspection failed to produce "
                "a patch proposal."
            )

        return WorkerResult(
            task_id=task.task_id,
            success=success,
            summary=summary,
            evidence=tuple(evidence),
            proposal=proposal_text,
            patches=tuple(patches)
        )