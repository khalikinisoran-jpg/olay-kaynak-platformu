from simulation.agent.worker.worker_agent import WorkerAgent
from simulation.agent.worker.worker_task import WorkerTask


class WorkerExecutor:

    def __init__(self):
        self.worker = WorkerAgent()

    def execute(self, agent, prompt):

        task = WorkerTask(
            task_id="worker-task",
            description=prompt,
            allowed_paths=(
                "tests/worker_contract_test.py",
            ),
            allowed_actions=(
                "read",
                "inspect",
                "propose",
            ),
            expected_output="patch proposal"
        )

        return self.worker.run(task)