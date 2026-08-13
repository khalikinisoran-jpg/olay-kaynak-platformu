from simulation.agent.controller.controller_decision import (
    ControllerDecision
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)

from simulation.security.governance_evaluator import (
    GovernanceEvaluator
)

from simulation.security.risk_engine import (
    RiskEngine
)


class ApplyAuthorization:

    """Fail-closed apply authorization boundary.

    The authorization never trusts duck-typed metadata. ``decision``
    must be a real ``ControllerDecision`` whose ``approved`` flag is
    exactly True and whose ``patch_fingerprint`` exactly matches the
    patch being applied.

    Every HIGH / CRITICAL / UNKNOWN apply requires an explicit,
    store-verified approval binding: the decision must reference a
    consumed approval (``approval_id``) that a store granted, released
    and bound to this exact patch object. A forged decision, an
    agent-claimed approval id, evidence-only metadata, a replayed
    approval or an approval bound to a different patch object all fail
    closed. **A missing approval store is itself a denial for
    HIGH/CRITICAL/UNKNOWN** (MISSION-018B): an unbound boundary can never
    authorize a security-sensitive write, so no runtime path -- including
    the bounded RECOVERY mode -- can mutate a HIGH/CRITICAL/UNKNOWN patch
    without an approval authority.

    LOW / MEDIUM applies are authorized on the typed-decision +
    fingerprint contract; this is safe because the risk level is
    recomputed deterministically from the patch at this boundary (never
    read from the forgeable decision) and MISSION-018A ensures only
    positively-classified non-suspicious content reaches LOW/MEDIUM.

    Since MISSION-019 the risk classification is performed by a single
    shared ``GovernanceEvaluator`` (the same one the pipeline and the
    approval console use), so the apply boundary can never diverge from
    the pipeline on which engine/policy to trust. The boundary keeps its
    own independent fail-closed checks (typed decision, ``approved is
    True``, fingerprint, store-backed approval) as defense in depth.
    """

    def __init__(
        self,
        approval_store=None,
        risk_engine=None,
        governance=None
    ):

        self.approval_store = approval_store

        if governance is not None:

            self.governance = governance

        elif risk_engine is not None:

            self.governance = GovernanceEvaluator(
                risk_engine=risk_engine
            )

        else:

            self.governance = GovernanceEvaluator()

    @property
    def risk_engine(self) -> RiskEngine:

        """Backward-compatible access to the evaluator's engine."""

        return self.governance.risk_engine

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

        return self.governance.authorize_apply(
            decision,
            patch,
            self.approval_store,
        )
