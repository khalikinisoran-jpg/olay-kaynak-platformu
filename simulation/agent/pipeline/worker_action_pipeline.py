from dataclasses import dataclass, field

from simulation.agent.apply.apply_authorization import (
    ApplyAuthorization
)

from simulation.agent.approval.approval import Approval

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

from simulation.agent.worker.validation_result import (
    ValidationResult
)

from simulation.agent.worker.worker_result import (
    WorkerResult
)

from simulation.security.governance_evaluator import (
    GovernanceEvaluator
)

from simulation.security.risk_engine import (
    RiskEngine
)

from simulation.security.risk_policy import (
    RiskPolicy
)


FAILURE_VALIDATION = "validation"

FAILURE_CONTROLLER = "controller"

FAILURE_APPLY = "apply"

FAILURE_VERIFICATION = "verification"

FAILURE_WORKER = "worker"

FAILURE_RISK = "risk"

FAILURE_APPROVAL = "approval"

FAILURE_ROLLBACK = "rollback"

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
    STAGE_RISK = "risk"
    STAGE_APPROVAL = "approval"

    def __init__(
        self,
        patch_validator=None,
        controller=None,
        apply_verify_pipeline=None,
        evidence_recorder=None,
        risk_engine=None,
        risk_policy=None,
        approval_store=None,
        approval_gateway=None,
        governance=None,
        apply_journal=None
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

        self.approval_store = approval_store

        self.approval_gateway = approval_gateway

        self.apply_journal = apply_journal

        if governance is not None:

            self.governance = governance

            self.risk_engine = governance.risk_engine

            self.risk_policy = governance.risk_policy

            self.risk_gate_enabled = True

        else:

            self.risk_engine = (
                risk_engine
                if risk_engine is not None
                else RiskEngine()
            )

            self.risk_policy = (
                risk_policy
                if risk_policy is not None
                else RiskPolicy()
            )

            self.governance = GovernanceEvaluator(
                risk_engine=self.risk_engine,
                risk_policy=self.risk_policy,
            )

            self.risk_gate_enabled = (
                risk_engine is not None
                and risk_policy is not None
            )

        self._bind_apply_journal()

        self._bind_approval_authority()

    def _bind_apply_journal(self):

        """Wire the optional apply-outcome journal into the pipeline.

        The journal records apply intent / outcome transitions around
        the real file write and verification. It is evidence of *what
        happened on disk*, never an authorization input. When no journal
        is supplied every record method is a no-op and behavior is
        unchanged.
        """

        if self.apply_journal is None:

            return

        executor = getattr(
            self.apply_verify_pipeline,
            "apply_executor",
            None,
        )

        pipeline = self.apply_verify_pipeline

        try:

            pipeline.journal = self.apply_journal

        except Exception:

            pass

        if executor is not None:

            try:

                executor.journal = self.apply_journal

            except Exception:

                pass

    def _bind_approval_authority(self):

        """Bind the apply boundary to the approval authority.

        When the risk gate is enabled the apply executor's
        authorization must re-verify the approval binding itself (not
        merely trust the pipeline) and must classify the patch with the
        *same* ``GovernanceEvaluator`` the pipeline uses (MISSION-019),
        so a caller-supplied custom engine can never drift between the
        pipeline gate and the apply boundary. Only a store-backed,
        shared-evaluator authorization can fail closed on forged
        decisions, agent-claimed approval ids and replayed approvals at
        the apply boundary.
        """

        if not self.risk_gate_enabled:

            return

        executor = getattr(
            self.apply_verify_pipeline,
            "apply_executor",
            None,
        )

        authorization = getattr(
            executor,
            "authorization",
            None,
        )

        if (
            isinstance(
                authorization,
                ApplyAuthorization,
            )
        ):

            executor.authorization = ApplyAuthorization(
                approval_store=self.approval_store,
                governance=self.governance,
            )

    def execute(
        self,
        worker_result: WorkerResult,
        verify_paths=None,
        test_targets=(),
        attempt=None
    ) -> WorkerPipelineResult:

        patches = tuple(
            worker_result.patches
        )

        recorder = self.evidence_recorder

        attempt_context = (
            attempt
            if (
                isinstance(attempt, int)
                and not isinstance(attempt, bool)
                and attempt >= 1
            )
            else 1
        )

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

        verification_depth = (
            ApplyVerifyPipeline.VERIFICATION_DEPTH_COMPILE_TESTS
        )

        for patch in patches:

            approval = None

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

            if self.risk_gate_enabled:

                governance_decision = self.governance.evaluate(
                    patch
                )

                if governance_decision.allowed is not True:

                    stages.append(
                        PatchStageResult(
                            patch=patch,
                            success=False,
                            stage=self.STAGE_RISK,
                            message=governance_decision.reason,
                        )
                    )

                    break

                if governance_decision.requires_human_approval:

                    approval = None

                    if self.approval_store is not None:

                        approval = (
                            self.approval_store.find_valid(
                                patch.fingerprint(),
                                path=patch.path,
                                action=patch.action,
                                risk_level=(
                                    governance_decision.risk_level.value
                                ),
                                attempt=attempt_context,
                                patch=patch,
                            )
                        )

                    valid, approval_reason = (
                        self._approval_is_valid(
                            approval,
                            patch,
                            governance_decision.risk_level.value,
                            attempt_context,
                        )
                    )

                    if (
                        not valid
                        and self.approval_gateway is not None
                        and self.approval_store is not None
                    ):

                        granted = (
                            self.approval_gateway.request_approval(
                                patch,
                                risk_level=(
                                    governance_decision.risk_level.value
                                ),
                                attempt=attempt_context,
                                evidence_reference=(
                                    worker_result.task_id
                                ),
                            )
                        )

                        if granted is not None:

                            approval = (
                                self.approval_store.find_valid(
                                    patch.fingerprint(),
                                    path=patch.path,
                                    action=patch.action,
                                    risk_level=(
                                        governance_decision.risk_level.value
                                    ),
                                    attempt=attempt_context,
                                    patch=patch,
                                )
                            )

                            valid, approval_reason = (
                                self._approval_is_valid(
                                    approval,
                                    patch,
                                    governance_decision.risk_level.value,
                                    attempt_context,
                                )
                            )

                    if not valid:

                        stages.append(
                            PatchStageResult(
                                patch=patch,
                                success=False,
                                stage=self.STAGE_APPROVAL,
                                message=(
                                    approval_reason
                                    if approval_reason
                                    else (
                                        "High-risk patch requires "
                                        "human approval."
                                    )
                                ),
                            )
                        )

                        break

                verification_depth = (
                    governance_decision.verification_depth
                )

            if approval is not None:

                decision = self.controller.approve(
                    patch,
                    ValidationResult(
                        valid=valid,
                        message=message,
                    ),
                    approval=approval,
                )

            else:

                decision = self.controller.approve(
                    patch,
                    ValidationResult(
                        valid=valid,
                        message=message,
                    ),
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
                verification_depth=verification_depth,
                attempt=attempt_context,
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

                if pipeline_result.rollback is not None:

                    recorder.record_rollback_result(
                        worker_result.task_id,
                        patch,
                        pipeline_result.rollback,
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
    def _approval_is_valid(
        approval,
        patch: PatchProposal,
        risk_level: str,
        attempt: int
    ):

        """Fail-closed validation of a returned approval.

        The pipeline never trusts whatever the approval store hands
        back. A usable approval must be a typed ``Approval`` bound to
        this exact patch fingerprint, path, action, risk context and
        attempt, and it must not be expired. Anything else (a missing
        record, a forged object, a substituted or downgraded context)
        is a denial. This keeps approval authority agent-independent:
        proposal-contained or store-injected approval metadata is
        never sufficient on its own.
        """

        if approval is None:

            return False, ""

        if not isinstance(approval, Approval):

            return False, (
                "Malformed approval: expected an Approval "
                "authorization record."
            )

        if approval.patch_fingerprint != patch.fingerprint():

            return False, (
                "Approval is bound to a different patch "
                "fingerprint."
            )

        if approval.path != patch.path:

            return False, (
                "Approval is bound to a different path."
            )

        if approval.action != patch.action:

            return False, (
                "Approval is bound to a different action."
            )

        if approval.risk_level != risk_level:

            return False, (
                "Approval is bound to a different risk context."
            )

        if approval.attempt != attempt:

            return False, (
                "Approval is bound to a different attempt."
            )

        if approval.is_expired():

            return False, "Approval has expired."

        return True, ""

    @staticmethod
    def _classify_failure(final: PatchStageResult) -> str:

        if final.success:

            return ""

        if final.stage == WorkerActionPipeline.STAGE_VALIDATION:

            return FAILURE_VALIDATION

        if final.stage == WorkerActionPipeline.STAGE_CONTROLLER:

            return FAILURE_CONTROLLER

        if final.stage == WorkerActionPipeline.STAGE_RISK:

            return FAILURE_RISK

        if final.stage == WorkerActionPipeline.STAGE_APPROVAL:

            return FAILURE_APPROVAL

        if final.stage == WorkerActionPipeline.STAGE_APPLY_VERIFY:

            if final.pipeline_result is not None:

                rollback = final.pipeline_result.rollback

                if (
                    rollback is not None
                    and not rollback.success
                ):

                    return FAILURE_ROLLBACK

                if final.pipeline_result.apply_success:

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
