from dataclasses import dataclass, field

from simulation.agent.pipeline.worker_action_pipeline import (
    WorkerPipelineResult
)

from simulation.agent.verify.verification_result import (
    VerificationEvidence
)

from simulation.agent.worker.worker_result import (
    WorkerResult
)


class AttemptStatus:

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


@dataclass(frozen=True)
class RecoveryAttempt:

    """Immutable record for a single bounded recovery attempt.

    A record is never mutated after creation. Later attempts append
    new records; they never overwrite earlier evidence.
    """

    attempt: int
    status: str
    worker_result: WorkerResult | None = None
    pipeline_result: WorkerPipelineResult | None = None
    failure_reason: str = ""
    evidence: tuple[VerificationEvidence, ...] = field(
        default_factory=tuple
    )
    patch_fingerprints: tuple[str, ...] = field(
        default_factory=tuple
    )
    failure_stage: str = ""

    @property
    def apply_result(self):

        if self.pipeline_result is None:

            return None

        stages = self.pipeline_result.patch_results

        if not stages:

            return None

        last = stages[-1]

        if last.pipeline_result is None:

            return None

        return last.pipeline_result.apply_result

    @property
    def verification(self):

        if self.pipeline_result is None:

            return None

        stages = self.pipeline_result.patch_results

        if not stages:

            return None

        last = stages[-1]

        if last.pipeline_result is None:

            return None

        return last.pipeline_result.verification

    @property
    def apply_success(self):

        result = self.apply_result

        return bool(
            result is not None
            and result.success
        )

    @property
    def verification_passed(self):

        result = self.verification

        return bool(
            result is not None
            and result.passed
        )
