from simulation.agent.controller.controller_decision import (
    ControllerDecision
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)

from simulation.security.risk_engine import (
    RiskEngine
)

from simulation.security.risk_level import (
    RiskLevel
)


class ApplyAuthorization:

    """Fail-closed apply authorization boundary.

    The authorization never trusts duck-typed metadata. ``decision``
    must be a real ``ControllerDecision`` whose ``approved`` flag is
    exactly True and whose ``patch_fingerprint`` exactly matches the
    patch being applied.

    When the boundary is bound to an approval authority (the
    ``ApprovalStore`` backing the risk gate), every HIGH / CRITICAL /
    UNKNOWN apply additionally requires an explicit, store-verified
    approval binding: the decision must reference a consumed approval
    (``approval_id``) that the store granted, released and bound to
    this exact patch object. A forged decision, an agent-claimed
    approval id, evidence-only metadata, a replayed approval or an
    approval bound to a different patch object all fail closed.

    The risk level is recomputed deterministically from the patch at
    this boundary, never read from the (forgeable) decision, so an
    attacker cannot downgrade a HIGH patch to skip the approval gate.
    """

    def __init__(self, approval_store=None, risk_engine=None):

        self.approval_store = approval_store

        self.risk_engine = (
            risk_engine
            if risk_engine is not None
            else RiskEngine()
        )

    def authorize(
        self,
        decision,
        patch: PatchProposal
    ) -> bool:

        if not isinstance(decision, ControllerDecision):

            return False

        if decision.approved is not True:

            return False

        if not decision.patch_fingerprint:

            return False

        if (
            decision.patch_fingerprint
            != patch.fingerprint()
        ):

            return False

        if self.approval_store is None:

            return True

        risk_level = self.risk_engine.classify(
            patch
        ).risk_level

        if risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM):

            return True

        if not decision.approval_id:

            return False

        return self.approval_store.authorize_apply(
            decision.approval_id,
            patch,
        )
