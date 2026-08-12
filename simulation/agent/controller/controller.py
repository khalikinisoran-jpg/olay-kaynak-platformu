from simulation.agent.approval.approval import Approval

from simulation.agent.controller.controller_decision import (
    ControllerDecision
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)

from simulation.agent.worker.validation_result import (
    ValidationResult
)


class Controller:

    def approve(
        self,
        patch: PatchProposal,
        validation: ValidationResult,
        approval: Approval | None = None
    ) -> ControllerDecision:

        if validation is None:

            return ControllerDecision(
                approved=False,
                reason="Missing validator result."
            )

        if not isinstance(
            validation,
            ValidationResult
        ):

            return ControllerDecision(
                approved=False,
                reason="Malformed validator result."
            )

        if validation.valid is not True:

            return ControllerDecision(
                approved=False,
                reason=(
                    "Controller rejected patch because "
                    "validator did not approve it."
                )
            )

        if patch.action != "modify":

            return ControllerDecision(
                approved=False,
                reason=(
                    "Controller rejected unsupported "
                    f"action: {patch.action}"
                )
            )

        if approval is not None and not isinstance(
            approval,
            Approval
        ):

            return ControllerDecision(
                approved=False,
                reason=(
                    "Controller rejected malformed "
                    "approval binding."
                )
            )

        if (
            approval is not None
            and approval.patch_fingerprint
            != patch.fingerprint()
        ):

            return ControllerDecision(
                approved=False,
                reason=(
                    "Controller rejected approval bound "
                    "to a different patch."
                )
            )

        return ControllerDecision(
            approved=True,
            reason=(
                "Controller approved validated patch."
            ),
            patch_fingerprint=patch.fingerprint(),
            approval_id=(
                approval.approval_id
                if approval is not None
                else ""
            )
        )
