from dataclasses import dataclass, field

from simulation.agent.controller.controller import Controller

from simulation.agent.controller.controller_decision import (
    ControllerDecision
)

from simulation.agent.pipeline.apply_verify_pipeline import (
    ApplyVerifyPipeline
)

from simulation.agent.pipeline.apply_verify_result import (
    ApplyVerifyResult
)

from simulation.agent.verify.verification_result import (
    VerificationEvidence
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)

from simulation.agent.worker.patch_validator import (
    PatchValidator
)

from simulation.agent.worker.worker_result import (
    WorkerResult
)


FAILURE_VALIDATION = "validation"

FAILURE_CONTROLLER = "controller"

FAILURE_APPLY = "apply"

FAILURE_VERIFICATION = "verification"

FAILURE_WORKER = "worker"

FAILURE_UNEXPECTED = "unexpected"


@dataclass(frozen=True)
class PatchStageResult:

    """Outcome for a single proposal inside the action pipeline.

    A stage is either a pre-apply gate (validation or controller)
    or the combined apply-and-verify run for the patch.
    """

    patch: PatchProposal
    success: bool
    stage: str
    message: str
    decision: ControllerDecision | None = None
    pipeline_result: ApplyVerifyResult | None = None


@dataclass(frozen=True)
class WorkerPipelineResult:

    """Final result the runtime hands to the upper flow.

    The worker only produces proposals. Every proposal must pass
    validation and controller approval before it is applied, and the
    pipeline fails closed whenever validation, controller, apply or
    verification fails. Verification evidence, stdout, stderr and the
    exit code are preserved for the caller.
    """

    success: bool
    worker_result: WorkerResult
    patch_results: tuple[PatchStageResult, ...] = field(
        default_factory=tuple
    )
    failure_reason: str = ""
    exit_code: int = 0
    stdout: str = ""
    stderr: str = ""
    evidence: tuple[VerificationEvidence, ...] = field(
        default_factory=tuple
    )
    verification_ran: bool = False
    failure_stage: str = ""

    @property
    def apply_success(self) -> bool:

        if not self.patch_results:

            return False

        if any(
            stage.pipeline_result is None
            for stage in self.patch_results
        ):

            return False

        return all(
            stage.pipeline_result.apply_result.success
            for stage in self.patch_results
        )

    @property
    def verification_passed(self) -> bool:

        if not self.patch_results:

            return False

        if any(
            stage.pipeline_result is None
            for stage in self.patch_results
        ):

            return False

        return all(
            stage.pipeline_result.verification_passed
            for stage in self.patch_results
        )


class WorkerActionPipeline:

    """Binds a WorkerResult to the apply-and-verify pipeline.

    Security contract, enforced per proposal in the exact order of the
    WorkerResult:

    1. Worker only proposes; it never applies by itself.
    2. PatchValidator must pass before Controller is consulted.
    3. Controller approval is required before apply runs.
    4. Apply must succeed before verification runs.
    5. Apply success is never treated as verification success.
    6. On the first failing proposal the pipeline stops; nothing later
       is applied or verified.
    """

    STAGE_VALIDATION = "validation"
    STAGE_CONTROLLER = "controller"
    STAGE_APPLY_VERIFY = "apply_verify"

    def __init__(
        self,
        patch_validator=None,
        controller=None,
        apply_verify_pipeline=None,
        evidence_recorder=None
    ):

        self.patch_validator = (
            patch_validator
            if patch_validator is not None
            else PatchValidator()
        )

        self.controller = (
            controller
            if controller is not None
            else Controller()
        )

        self.apply_verify_pipeline = (
            apply_verify_pipeline
            if apply_verify_pipeline is not None
            else ApplyVerifyPipeline()
        )

        self.evidence_recorder = evidence_recorder

    def execute(
        self,
        worker_result: WorkerResult,
        verify_paths=None,
        test_targets=()
    ) -> WorkerPipelineResult:

        patches = tuple(
            worker_result.patches
        )

        recorder = self.evidence_recorder

        if recorder is not None:

            recorder.record_task_created(
                worker_result
            )

            recorder.record_inspection(
                worker_result
            )

        if not patches:

            return WorkerPipelineResult(
                success=False,
                worker_result=worker_result,
                failure_reason=(
                    "Worker produced no patch proposals."
                ),
                exit_code=-1,
                failure_stage=FAILURE_WORKER,
            )

        stages = []

        verification_ran = False

        for patch in patches:

            if recorder is not None:

                recorder.record_patch_proposed(
                    worker_result.task_id,
                    patch,
                )

            valid, message = (
                self.patch_validator.validate(
                    patch
                )
            )

            if recorder is not None:

                recorder.record_patch_validated(
                    worker_result.task_id,
                    patch,
                    valid,
                    message,
                )

            if not valid:

                stages.append(
                    PatchStageResult(
                        patch=patch,
                        success=False,
                        stage=self.STAGE_VALIDATION,
                        message=message,
                    )
                )

                break

            decision = self.controller.approve(
                patch,
                message,
            )

            if recorder is not None:

                recorder.record_controller_decision(
                    worker_result.task_id,
                    patch,
                    decision,
                )

            if decision.approved is not True:

                stages.append(
                    PatchStageResult(
                        patch=patch,
                        success=False,
                        stage=self.STAGE_CONTROLLER,
                        message=decision.reason,
                        decision=decision,
                    )
                )

                break

            pipeline_result = self.apply_verify_pipeline.execute(
                patch,
                decision,
                verify_paths=verify_paths,
                test_targets=test_targets,
            )

            if recorder is not None:

                recorder.record_apply_result(
                    worker_result.task_id,
                    patch,
                    pipeline_result.apply_result,
                )

                if pipeline_result.verification is not None:

                    recorder.record_verification_result(
                        worker_result.task_id,
                        patch,
                        pipeline_result.verification,
                    )

            if pipeline_result.verification_ran:

                verification_ran = True

            stages.append(
                PatchStageResult(
                    patch=patch,
                    success=pipeline_result.success,
                    stage=self.STAGE_APPLY_VERIFY,
                    message=pipeline_result.failure_reason,
                    decision=decision,
                    pipeline_result=pipeline_result,
                )
            )

            if not pipeline_result.success:

                break

        final = stages[-1]

        executed = [
            stage
            for stage in stages
            if stage.pipeline_result is not None
        ]

        evidence = tuple(
            record
            for stage in executed
            for record in stage.pipeline_result.evidence
        )

        return WorkerPipelineResult(
            success=final.success,
            worker_result=worker_result,
            patch_results=tuple(stages),
            failure_reason=(
                ""
                if final.success
                else final.message
            ),
            failure_stage=WorkerActionPipeline._classify_failure(
                final
            ),
            exit_code=(
                final.pipeline_result.exit_code
                if final.pipeline_result is not None
                else -1
            ),
            stdout=self._join_outputs(
                stage.pipeline_result.stdout
                for stage in executed
            ),
            stderr=self._join_outputs(
                stage.pipeline_result.stderr
                for stage in executed
            ),
            evidence=evidence,
            verification_ran=verification_ran,
        )

    @staticmethod
    def _classify_failure(final: PatchStageResult) -> str:

        if final.success:

            return ""

        if final.stage == WorkerActionPipeline.STAGE_VALIDATION:

            return FAILURE_VALIDATION

        if final.stage == WorkerActionPipeline.STAGE_CONTROLLER:

            return FAILURE_CONTROLLER

        if final.stage == WorkerActionPipeline.STAGE_APPLY_VERIFY:

            if (
                final.pipeline_result is not None
                and final.pipeline_result.apply_success
            ):

                return FAILURE_VERIFICATION

            return FAILURE_APPLY

        return FAILURE_UNEXPECTED

    @staticmethod
    def _join_outputs(outputs):

        return "\n".join(
            output
            for output in outputs
            if output
        )
