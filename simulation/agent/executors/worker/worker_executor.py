from simulation.agent.worker.worker_agent import WorkerAgent
from simulation.agent.worker.worker_task import WorkerTask


class WorkerExecutor:

    DEFAULT_ALLOWED_PATHS = ()

    def __init__(
        self,
        worker=None,
        allowed_paths=DEFAULT_ALLOWED_PATHS
    ):

        self.worker = (
            worker
            if worker is not None
            else WorkerAgent()
        )

        self.allowed_paths = tuple(
            allowed_paths
        )

    def execute(
        self,
        agent,
        prompt,
        attempt=None,
        recovery_evidence=()
    ):

        task = WorkerTask(
            task_id="worker-task",
            description=prompt,
            allowed_paths=self.allowed_paths,
            allowed_actions=(
                "read",
                "inspect",
                "propose",
            ),
            expected_output="patch proposal",
            attempt=attempt,
            recovery_evidence=tuple(recovery_evidence)
        )

        return self.worker.run(task)