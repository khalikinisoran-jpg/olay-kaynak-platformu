from simulation.agent.controller.controller_decision import (
    ControllerDecision
)


class ApplyAuthorization:

    def authorize(
        self,
        decision: ControllerDecision
    ) -> bool:

        return (
            decision.approved is True
        )