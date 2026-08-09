from simulation.agent.controller.controller_decision import (
    ControllerDecision
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)


class ApplyAuthorization:

    def authorize(
        self,
        decision: ControllerDecision,
        patch: PatchProposal
    ) -> bool:

        if decision.approved is not True:

            return False

        if not decision.patch_fingerprint:

            return False

        return (
            decision.patch_fingerprint
            == patch.fingerprint()
        )