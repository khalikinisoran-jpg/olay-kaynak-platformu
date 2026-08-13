"""Minimal, safe CLI human-approval interface (MISSION-017).

This module turns a HIGH/CRITICAL proposal into a human-readable
approval request, collects a real human approve/deny decision, and on
approval routes it into the existing ``ApprovalStore`` authority. It is
a thin UX layer only: it never makes the pipeline or the apply boundary
trust agent-controlled metadata, and it never becomes an authority on
its own. Every value it displays and every value it grants is derived
from the actual ``PatchProposal`` object and the deterministic
``RiskAssessment``, so the displayed context, the granted context and
the context the apply boundary re-verifies are the same by construction.

Security invariants (all enforced downstream and re-asserted here):

- AGENT-CONTROLLED ``approved=True`` claims are never consulted; the
  only way to create an approval is ``ApprovalStore.grant`` with a
  context derived from the real patch + system-derived risk.
- Displayed patch == granted patch == applied patch: the grant is
  fingerprint-bound to the exact patch object; any substitution fails
  closed at the store ``find_valid`` / apply ``authorize_apply``.
- Shown risk == real risk: the console recomputes the risk with the
  system ``RiskEngine``; if the pipeline-provided risk differs, the
  console refuses (returns ``None``) instead of displaying a lower risk.
- The decision is fail-closed: only an explicit approve phrase grants;
  deny, EOF or unrecognized input never produce an approval.
- Human approval metadata alone is never authority: the grant still
  goes through the store and the store/apply boundary still enforce
  fingerprint/path/action/risk/attempt/object-identity binding.

The renderer is secret-safe: it prints fingerprint/path/action/risk/
attempt/expiry/authorizer/evidence-reference, never patch old/new
content.
"""

from dataclasses import dataclass

from simulation.agent.approval.approval import (
    Approval,
    iso_in_future,
    now_iso,
)

from simulation.agent.approval.approval_store import ApprovalStore

from simulation.agent.worker.patch_proposal import PatchProposal

from simulation.security.governance_evaluator import (
    GovernanceEvaluator,
)

from simulation.security.risk_engine import (
    RiskAssessment,
    RiskEngine,
)


APPROVE_PHRASES = frozenset({
    "approve",
    "onayla",
    "yes",
    "y",
    "evet",
    "onay",
})

DENY_PHRASES = frozenset({
    "deny",
    "reddet",
    "no",
    "n",
    "hayir",
    "hayır",
    "red",
})


@dataclass(frozen=True)
class PendingApprovalRequest:

    """Immutable, human-readable snapshot of a pending HIGH/CRITICAL
    authorization decision.

    The request always holds the real ``PatchProposal`` and the real
    ``RiskAssessment`` so every displayed and granted value is derived
    from the authoritative objects, never from agent-carried metadata.
    """

    patch: PatchProposal
    assessment: RiskAssessment
    attempt: int
    authorizer: str
    ttl_seconds: int
    evidence_reference: str
    created_at: str

    @property
    def fingerprint(self) -> str:

        return self.patch.fingerprint()

    @property
    def path(self) -> str:

        return self.patch.path

    @property
    def action(self) -> str:

        return self.patch.action

    @property
    def risk_level(self) -> str:

        return self.assessment.risk_level.value

    @property
    def risk_reason(self) -> str:

        return self.assessment.reason

    @property
    def expires_at(self) -> str:

        return iso_in_future(self.ttl_seconds)

    def render(self) -> str:

        """Human-readable rendering of the full approval context."""

        return (
            "\n"
            "=" * 62 + "\n"
            " HUMAN APPROVAL REQUEST\n"
            "=" * 62 + "\n"
            f" PATCH FINGERPRINT : {self.fingerprint}\n"
            f" PATH               : {self.path}\n"
            f" ACTION             : {self.action}\n"
            f" RISK LEVEL         : {self.risk_level}\n"
            f" RISK CONTEXT       : {self.risk_reason}\n"
            f" ATTEMPT            : {self.attempt}\n"
            f" AUTHORIZER         : {self.authorizer}\n"
            f" CREATED AT         : {self.created_at}\n"
            f" EXPIRES AT         : {self.expires_at} "
            f"(TTL {self.ttl_seconds}s)\n"
            f" EVIDENCE REFERENCE : {self.evidence_reference}\n"
            "=" * 62
        )

    def to_grant_context(self) -> dict:

        """Grant context derived from the real patch + assessment.

        Every value is recomputed from the authoritative objects; a
        mutated or substituted object would change the fingerprint and
        therefore fail the downstream fingerprint binding.
        """

        return {
            "patch_fingerprint": self.patch.fingerprint(),
            "path": self.patch.path,
            "action": self.patch.action,
            "risk_level": self.assessment.risk_level.value,
            "attempt": self.attempt,
            "authorizer": self.authorizer,
            "expires_at": self.ttl_seconds,
        }


def build_pending_request(
    patch,
    assessment,
    attempt=1,
    authorizer="human",
    ttl_seconds=3600,
    evidence_reference="",
) -> PendingApprovalRequest:

    """Typed factory for a pending approval request.

    ``patch`` must be a real ``PatchProposal`` and ``assessment`` a
    real ``RiskAssessment``; malformed inputs fail closed (raise) so a
    request can never be built from garbage or duck-typed metadata.
    """

    if not isinstance(patch, PatchProposal):

        raise TypeError(
            "Pending approval request requires a PatchProposal."
        )

    if not isinstance(assessment, RiskAssessment):

        raise TypeError(
            "Pending approval request requires a RiskAssessment."
        )

    if (
        not isinstance(attempt, int)
        or isinstance(attempt, bool)
        or attempt < 1
    ):

        raise ValueError(
            "Pending approval request attempt must be a "
            "positive integer."
        )

    if not isinstance(ttl_seconds, int) or ttl_seconds < 1:

        raise ValueError(
            "Pending approval request TTL must be a "
            "positive integer."
        )

    if not isinstance(authorizer, str) or not authorizer:

        raise ValueError(
            "Pending approval request authorizer is missing."
        )

    return PendingApprovalRequest(
        patch=patch,
        assessment=assessment,
        attempt=attempt,
        authorizer=authorizer,
        ttl_seconds=ttl_seconds,
        evidence_reference=(
            evidence_reference
            if isinstance(evidence_reference, str)
            else ""
        ),
        created_at=now_iso(),
    )


def prompt_approval_decision(
    request: PendingApprovalRequest,
    store: ApprovalStore,
    input_fn=input,
    print_fn=print,
) -> Approval | None:

    """Interactive CLI approval decision.

    Renders the full request, then asks the human. Only an explicit
    approve phrase grants; deny, EOF or unrecognized input fail closed
    (return ``None`` and never grant). On approve, the approval is
    granted through the store with the request's derived context and
    returned.

    ``input_fn`` / ``print_fn`` are injectable for deterministic tests.
    """

    while True:

        print_fn(request.render())

        try:

            decision = input_fn(
                "\nApprove this patch? (approve/deny): "
            ).strip().lower()

        except EOFError:

            print_fn("No input; approval denied.")
            return None

        if decision in APPROVE_PHRASES:

            approval = store.grant(
                **request.to_grant_context()
            )

            print_fn(
                "Approval granted and recorded as "
                "WorkerHumanApprovalGranted."
            )

            return approval

        if decision in DENY_PHRASES:

            print_fn("Approval denied.")
            return None

        print_fn(
            "Unrecognized input. Type 'approve' or 'deny'."
        )


class ConsoleApprovalGateway:

    """Bridge that the governed pipeline consults when a HIGH/CRITICAL
    proposal has no valid approval in the store.

    The gateway recomputes the risk with the system ``RiskEngine`` and
    refuses (``None``) when the pipeline-provided risk differs from the
    recomputed one, so the risk shown to the human is always the real
    system-derived risk. On explicit human approval it grants through
    the store and returns the ``Approval``; the pipeline then consumes
    the approval via ``ApprovalStore.find_valid`` (which binds it to the
    exact patch object), so authority stays entirely in the store.
    """

    def __init__(
        self,
        store: ApprovalStore,
        risk_engine=None,
        governance=None,
        input_fn=input,
        print_fn=print,
        authorizer="human",
        ttl_seconds=3600,
    ):

        self.store = store

        if governance is not None:

            self.governance = governance

            self.risk_engine = governance.risk_engine

        else:

            self.risk_engine = (
                risk_engine
                if risk_engine is not None
                else RiskEngine()
            )

            self.governance = GovernanceEvaluator(
                risk_engine=self.risk_engine
            )

        self.input_fn = input_fn

        self.print_fn = print_fn

        self.authorizer = authorizer

        self.ttl_seconds = ttl_seconds

    def request_approval(
        self,
        patch,
        risk_level,
        attempt,
        evidence_reference="",
    ) -> Approval | None:

        """Render + decide for a pending approval.

        Returns a granted ``Approval`` on explicit human approve, or
        ``None`` on deny / mismatch. Never returns an approval on its
        own: the grant is routed through ``self.store``.
        """

        assessment = self.governance.classify(patch)

        if not isinstance(assessment, RiskAssessment):

            return None

        if assessment.risk_level.value != risk_level:

            self.print_fn(
                "Approval refused: shown risk does not match "
                "the system-derived risk."
            )

            return None

        request = build_pending_request(
            patch=patch,
            assessment=assessment,
            attempt=attempt,
            authorizer=self.authorizer,
            ttl_seconds=self.ttl_seconds,
            evidence_reference=evidence_reference,
        )

        return prompt_approval_decision(
            request,
            self.store,
            input_fn=self.input_fn,
            print_fn=self.print_fn,
        )
