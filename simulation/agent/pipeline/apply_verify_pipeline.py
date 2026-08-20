from dataclasses import replace

from simulation.agent.apply.apply_executor import (
    ApplyExecutor
)

from simulation.agent.controller.controller_decision import (
    ControllerDecision
)

from simulation.agent.pipeline.apply_verify_result import (
    ApplyVerifyResult,
    RollbackResult,
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

    When verification FAILS after a successful apply, the pipeline
    rolls the target back to its exact pre-apply content (via the
    apply executor's ``rollback``) and, when supported, re-verifies
    the clean state with a compile-only check. A rollback failure is
    reported in ``ApplyVerifyResult.rollback`` so the upper flow can
    treat it as a terminal, non-retryable outcome instead of retrying
    on a corrupted or unknown state.

    When an ``apply_outcome_journal`` is wired (MISSION-019) the
    pipeline records the terminal VERIFIED / ROLLED_BACK /
    ROLLBACK_FAILED outcome against the ``intent_id`` produced by the
    apply executor, so a crash between the file write and the evidence
    event is always detectable after restart. The journal is durable
    outcome evidence, never an authorization input.
    """

    VERIFICATION_DEPTH_COMPILE = "compile"

    VERIFICATION_DEPTH_COMPILE_TESTS = "compile+tests"

    def __init__(
        self,
        apply_executor=None,
        verification_executor=None,
        journal=None
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

        self.journal = (
            journal
            if journal is not None
            else getattr(
                self.apply_executor,
                "journal",
                None,
            )
        )

    def execute(
        self,
        patch: PatchProposal,
        decision: ControllerDecision,
        verify_paths=None,
        test_targets=(),
        verification_depth=VERIFICATION_DEPTH_COMPILE_TESTS,
        attempt=None,
        scope=None
    ) -> ApplyVerifyResult:

        apply_result = self.apply_executor.apply(
            patch,
            decision,
            attempt=attempt,
            scope=scope,
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

        if verification_result.passed:

            self._record_verified(
                apply_result.intent_id
            )

            return ApplyVerifyResult(
                apply_result=apply_result,
                verification=verification_result,
                success=True,
                verification_ran=True,
            )

        rollback = self._rollback(
            patch,
            verify_paths,
            apply_result.intent_id,
            scope,
        )

        return ApplyVerifyResult(
            apply_result=apply_result,
            verification=verification_result,
            success=False,
            verification_ran=True,
            rollback=rollback,
        )

    def _record_verified(self, intent_id):

        if self.journal is None or not intent_id:

            return

        self.journal.record_verified(
            intent_id
        )

    def _record_rollback_outcome(self, intent_id, rollback):

        if self.journal is None or not intent_id:

            return

        if rollback is None:

            return

        if rollback.success:

            self.journal.record_rolled_back(
                intent_id
            )

        else:

            self.journal.record_rollback_failed(
                intent_id
            )

    def _rollback(
        self,
        patch: PatchProposal,
        verify_paths,
        intent_id,
        scope=None,
    ):

        rollback_fn = getattr(
            self.apply_executor,
            "rollback",
            None,
        )

        if rollback_fn is None:

            return None

        if self.journal is not None and intent_id:

            self.journal.record_rollback_started(
                intent_id
            )

        ok, message = rollback_fn(
            patch,
            scope=scope,
        )

        rollback = RollbackResult(
            success=ok,
            path=patch.path,
            message=message,
            restore_verified=ok,
        )

        self._record_rollback_outcome(
            intent_id,
            rollback,
        )

        if not ok:

            return rollback

        clean_verify = self._verify_clean_state(
            patch,
            verify_paths,
        )

        if clean_verify is None:

            return rollback

        return replace(
            rollback,
            clean_verified=bool(clean_verify.passed),
            clean_verification=clean_verify,
        )

    def _verify_clean_state(
        self,
        patch: PatchProposal,
        verify_paths,
    ):

        compile_verify = getattr(
            self.verification_executor,
            "verify_python_compile",
            None,
        )

        if compile_verify is None:

            return None

        return compile_verify(
            paths=(
                tuple(verify_paths)
                if verify_paths
                else (patch.path,)
            ),
        )
