from simulation.agent.apply.apply_executor import (
    ApplyExecutor
)

from simulation.agent.controller.controller_decision import (
    ControllerDecision
)

from simulation.agent.pipeline.apply_verify_result import (
    ApplyVerifyResult
)

from simulation.agent.verify.verification_executor import (
    VerificationExecutor
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)


class ApplyVerifyPipeline:

    """Runs verification after a successful patch application.

    Apply and verification are always distinct outcomes. A pipeline
    result succeeds only when the patch applied and the verification
    passed. Verification never runs when the patch fails to apply.
    """

    VERIFICATION_DEPTH_COMPILE = "compile"

    VERIFICATION_DEPTH_COMPILE_TESTS = "compile+tests"

    def __init__(
        self,
        apply_executor=None,
        verification_executor=None
    ):

        self.apply_executor = (
            apply_executor
            if apply_executor is not None
            else ApplyExecutor()
        )

        self.verification_executor = (
            verification_executor
            if verification_executor is not None
            else VerificationExecutor()
        )

    def execute(
        self,
        patch: PatchProposal,
        decision: ControllerDecision,
        verify_paths=None,
        test_targets=(),
        verification_depth=VERIFICATION_DEPTH_COMPILE_TESTS
    ) -> ApplyVerifyResult:

        apply_result = self.apply_executor.apply(
            patch,
            decision
        )

        if not apply_result.success:

            return ApplyVerifyResult(
                apply_result=apply_result,
                verification=None,
                success=False,
                verification_ran=False,
            )

        if verification_depth == (
            self.VERIFICATION_DEPTH_COMPILE
        ):

            verification_result = (
                self.verification_executor.verify_python_compile(
                    paths=(
                        tuple(verify_paths)
                        if verify_paths
                        else (patch.path,)
                    ),
                )
            )

        else:

            verification_result = (
                self.verification_executor.verify(
                    paths=(
                        tuple(verify_paths)
                        if verify_paths
                        else (patch.path,)
                    ),
                    test_targets=tuple(
                        test_targets
                    ),
                )
            )

        return ApplyVerifyResult(
            apply_result=apply_result,
            verification=verification_result,
            success=verification_result.passed,
            verification_ran=True,
        )
