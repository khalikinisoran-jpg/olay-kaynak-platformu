"""Single deterministic governance authority (MISSION-019).

The governed runtime evaluates a proposal in three places that must
never disagree:

- the pipeline risk gate  (``WorkerActionPipeline``)
- the approval console    (``ConsoleApprovalGateway`` risk display)
- the apply boundary      (``ApplyAuthorization``)

Each of those places used to construct or receive its *own*
``RiskEngine``/``RiskPolicy``, so a caller who wired a custom engine
into the pipeline while the apply boundary kept the default engine
could make the three layers classify the same patch differently.
``GovernanceEvaluator`` collapses that: it wraps exactly one
``RiskEngine`` + ``RiskPolicy`` and every layer that needs a governance
decision consumes *this* evaluator. The apply boundary therefore
recomputes the risk with the same authority the pipeline used, while
still performing its own independent fail-closed checks
(MISSION-014 / MISSION-018B preserved).

Security invariants this component is required to preserve:

- MISSION-018A: ``RiskEngine`` keeps the SAFE / SUSPICIOUS / OPAQUE
  fail-closed content classification; ``not detected`` is never
  treated as ``safe``; OPAQUE -> UNKNOWN -> policy DENY; SUSPICIOUS
  -> HIGH; PEM -> CRITICAL; LOW/MEDIUM keep the existing positive
  SAFE-classification auto-apply semantics. The evaluator never
  modifies the engine or the policy; it only fixes *which* engine and
  policy are consulted.
- MISSION-018B: the apply boundary still requires a store-verified,
  single-use approval for every HIGH / CRITICAL / UNKNOWN apply and a
  missing approval store is itself a denial. ``authorize_apply`` keeps
  exactly that contract; the evaluator only changes *how* the risk
  level is obtained (from the shared engine, never from the forgeable
  decision object).
"""

from dataclasses import dataclass

from simulation.security.risk_engine import (
    RiskAssessment,
    RiskEngine,
)

from simulation.security.risk_level import (
    RiskLevel,
)

from simulation.security.risk_policy import (
    RiskDecision,
    RiskPolicy,
)


@dataclass(frozen=True)
class GovernanceDecision:

    """The single governance outcome for one proposal.

    Bundles the deterministic ``RiskAssessment`` and the
    ``RiskDecision`` so every consumer (pipeline gate, approval console,
    apply boundary) reads the same verdict instead of recomputing
    fragments of it.
    """

    risk_level: RiskLevel
    assessment: RiskAssessment
    policy: RiskDecision
    allowed: bool
    requires_human_approval: bool
    allow_auto_apply: bool
    max_attempts: int
    verification_depth: str
    reason: str

    @classmethod
    def from_assessment(
        cls,
        assessment: RiskAssessment,
        policy: RiskDecision,
    ) -> "GovernanceDecision":

        return cls(
            risk_level=assessment.risk_level,
            assessment=assessment,
            policy=policy,
            allowed=policy.allowed,
            requires_human_approval=policy.requires_human_approval,
            allow_auto_apply=policy.allow_auto_apply,
            max_attempts=policy.max_attempts,
            verification_depth=policy.verification_depth,
            reason=policy.reason or assessment.reason,
        )


class GovernanceEvaluator:

    """Deterministic, immutable-in-behavior governance authority.

    One evaluator is constructed with one ``RiskEngine`` and one
    ``RiskPolicy``; every governed layer that shares this evaluator
    therefore agrees on risk classification by construction. The
    evaluator itself is stateless and deterministic: the same patch
    always yields the same ``GovernanceDecision`` for a given engine
    and policy.

    ``authorize_apply`` is the shared apply-boundary authorization
    check. It is deliberately *not* the whole boundary: the caller
    (``ApplyAuthorization``) still enforces the typed
    ``ControllerDecision``, the exact ``approved is True`` contract and
    the fingerprint match before delegating here. This method only
    decides the risk-dependent branch using the shared engine. The
    decision object is accessed duck-typed (``approval_id``) so this
    security-layer module never depends on agent-layer types.
    """

    def __init__(self, risk_engine=None, risk_policy=None):

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

    def classify(
        self,
        patch,
        advisory_risk=None,
        advisory_confidence=None,
    ) -> RiskAssessment:

        """Delegate to the shared ``RiskEngine`` (unchanged semantics)."""

        return self.risk_engine.classify(
            patch,
            advisory_risk,
            advisory_confidence,
        )

    def decide(self, assessment) -> RiskDecision:

        """Delegate to the shared ``RiskPolicy`` (unchanged semantics)."""

        return self.risk_policy.decide(assessment)

    def evaluate(
        self,
        patch,
        advisory_risk=None,
        advisory_confidence=None,
    ) -> GovernanceDecision:

        """One deterministic governance verdict for a proposal."""

        assessment = self.classify(
            patch,
            advisory_risk,
            advisory_confidence,
        )

        policy = self.decide(assessment)

        return GovernanceDecision.from_assessment(
            assessment,
            policy,
        )

    def authorize_apply(
        self,
        decision,
        patch,
        approval_store,
    ) -> bool:

        """Apply-boundary authorization using this evaluator's engine.

        Risk is recomputed deterministically from the patch with the
        *shared* engine (never read from the forgeable decision), so
        the apply boundary and the pipeline cannot diverge.

        - LOW / MEDIUM -> the typed-decision + fingerprint contract
          (safe only because MISSION-018A keeps positively-classified
          SAFE content at LOW/MEDIUM).
        - HIGH / CRITICAL / UNKNOWN -> requires ``decision.approval_id``
          verified by ``approval_store.authorize_apply``; a missing
          approval store is itself a denial (MISSION-018B).
        """

        risk_level = self.classify(patch).risk_level

        if risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM):

            return True

        if approval_store is None:

            return False

        approval_id = getattr(decision, "approval_id", None)

        if not approval_id:

            return False

        return approval_store.authorize_apply(
            approval_id,
            patch,
        )
