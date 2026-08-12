from simulation.agent.apply.apply_authorization import (
    ApplyAuthorization
)

from simulation.agent.apply.apply_result import (
    ApplyResult
)

from simulation.agent.apply.file_applier import (
    FileApplier
)

from simulation.agent.controller.controller_decision import (
    ControllerDecision
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)


class ApplyExecutor:

    def __init__(self, approval_store=None):

        self.authorization = (
            ApplyAuthorization(
                approval_store=approval_store,
            )
        )

        self.file_applier = (
            FileApplier()
        )

    def apply(
        self,
        patch: PatchProposal,
        decision: ControllerDecision
    ) -> ApplyResult:

        if not self.authorization.authorize(
            decision,
            patch
        ):

            return ApplyResult(
                success=False,
                path=patch.path,
                message=(
                    "Apply denied: "
                    "Controller approval does not "
                    "match this patch."
                )
            )

        success, message = (
            self.file_applier.apply(
                patch
            )
        )

        return ApplyResult(
            success=success,
            path=patch.path,
            message=message
        )

    def rollback(
        self,
        patch: PatchProposal
    ) -> tuple[bool, str]:

        """Restore the patch target to its exact pre-apply content.

        Used by the apply/verify pipeline to roll a failed patch back
        before any recovery retry so retries never build on top of a
        corrupted or failed-verification state.
        """

        return self.file_applier.restore(
            patch
        )