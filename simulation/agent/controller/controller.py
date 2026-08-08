from simulation.agent.controller.controller_decision import (
    ControllerDecision
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)


class Controller:

    def approve(
        self,
        patch: PatchProposal,
        validation_message: str
    ) -> ControllerDecision:

        if not validation_message:
            return ControllerDecision(
                approved=False,
                reason="Missing validator result."
            )

        if validation_message != (
            "Patch validation passed."
        ):
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

        return ControllerDecision(
            approved=True,
            reason=(
                "Controller approved validated patch."
            )
        )