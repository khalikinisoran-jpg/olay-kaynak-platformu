from pathlib import Path

from simulation.agent.worker.analysis_result import (
    AnalysisResult
)

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

from simulation.security.secret_policy import (
    REDACTED_MARKER,
    is_secret_file,
    redact_content,
    sanitize_for_llm,
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

    REQUIRED_ACTIONS = (
        "read",
        "inspect",
        "propose",
    )

    def run(
        self,
        task: WorkerTask
    ) -> WorkerResult:

        for action in self.REQUIRED_ACTIONS:

            if not self.policy.allows(action):

                return WorkerResult(
                    task_id=task.task_id,
                    success=False,
                    summary=f"Worker policy denied {action} action."
                )

            if not self._task_allows(task, action):

                return WorkerResult(
                    task_id=task.task_id,
                    success=False,
                    summary=f"Worker policy denied {action} action."
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

            if is_secret_file(path_value):

                evidence.append({
                    "path": path_value,
                    "action": "inspect",
                    "status": "skipped_secret",
                    "error": (
                        "Secret file skipped; content is "
                        "never sent to the analyzer."
                    )
                })

                continue

            try:

                raw_content = path.read_text(
                    encoding="utf-8"
                )

                analysis_content, _ = redact_content(
                    raw_content
                )

                evidence.append({
                    "path": path_value,
                    "action": "read",
                    "status": "success",
                    "characters": len(raw_content)
                })

                (
                    analysis
                ) = self.llm_analyzer.analyze(
                    path=path_value,
                    content=analysis_content,
                    description=self._analysis_description(
                        task
                    )
                )

                if not isinstance(
                    analysis,
                    AnalysisResult
                ):

                    raise ValueError(
                        "Analyzer must return an "
                        "AnalysisResult."
                    )

                diagnosis = analysis.diagnosis

                old_text = analysis.old_text

                new_text = analysis.new_text

                if raw_content.count(old_text) != 1:

                    raise ValueError(
                        "LLM old_text must occur exactly "
                        "once in the current file."
                    )

                if REDACTED_MARKER in new_text:

                    raise ValueError(
                        "Proposal references redacted "
                        "secret content; rejected."
                    )

                new_content = raw_content.replace(
                    old_text,
                    new_text,
                    1
                )

                patch = PatchProposal(
                    path=path_value,
                    action="modify",
                    reason=diagnosis,
                    old_content=raw_content,
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

    @staticmethod
    def _task_allows(task, action) -> bool:

        if not task.allowed_actions:

            return True

        return action in task.allowed_actions

    @staticmethod
    def _analysis_description(task) -> str:

        description = task.description

        if not task.recovery_evidence:

            return description

        evidence_lines = [
            WorkerAgent._format_evidence_line(record)
            for record in task.recovery_evidence
        ]

        return (
            description
            + "\n\nPREVIOUS ATTEMPT FAILURE EVIDENCE "
            f"(attempt {task.attempt}):\n"
            + "\n".join(evidence_lines)
        )

    @staticmethod
    def _format_evidence_line(record) -> str:

        return (
            f"- {record.stage}: "
            f"exit_code={record.exit_code} "
            f"stdout={sanitize_for_llm(record.stdout)!r} "
            f"stderr={sanitize_for_llm(record.stderr)!r}"
        )