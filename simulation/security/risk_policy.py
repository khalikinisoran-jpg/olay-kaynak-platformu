from dataclasses import dataclass

from simulation.security.risk_engine import RiskAssessment

from simulation.security.risk_level import RiskLevel


@dataclass(frozen=True)
class RiskDecision:

    """Executable policy outcome for a risk assessment.

    ``allowed`` is the hard gate: ``False`` (unknown/malformed risk,
    missing policy) means the proposal is DENIED unconditionally.
    ``requires_human_approval`` marks approvals for HIGH/CRITICAL.
    ``allow_auto_apply`` is True only when the proposal may flow to
    apply/verification without any human authorization.
    ``max_attempts`` is the retry allowance for this risk level and
    never exceeds the recovery engine's hard cap.
    ``verification_depth`` is the verification scope for the proposal.
    """

    risk_level: RiskLevel
    allowed: bool
    requires_human_approval: bool
    allow_auto_apply: bool
    max_attempts: int
    verification_depth: str
    reason: str = ""


class RiskPolicy:

    """Fail-closed mapping from risk to enforceable requirements.

    Fail-closed rules:

    - Missing or malformed assessment -> DENY (``allowed`` is False).
    - UNKNOWN risk -> DENY (never auto-approvable).
    - HIGH / CRITICAL -> human approval required; never auto-applied.
    - LOW / MEDIUM -> automatic path (subject to the normal
      validation/controller/apply/verification gates).
    - Retry allowance is capped per level and never exceeds the
      recovery engine hard cap of 3.

    LOW / MEDIUM security assumption (MISSION-018A): auto-apply for LOW /
    MEDIUM is safe ONLY because ``RiskEngine`` now classifies content into
    three states before a level is produced -- SAFE (plain content), which
    may keep a LOW/MEDIUM baseline; SUSPICIOUS (credential-like material),
    which is always elevated to HIGH so it never reaches this automatic
    path; and OPAQUE (unparseable/control-character content), which yields
    UNKNOWN so it is DENIED here. ``not detected`` is never treated as
    ``safe``. False negatives are bounded by (1) the expanded structural
    suspicion detection, (2) the OPAQUE -> UNKNOWN fail-closed path, (3)
    the worker/apply path scope enforcement, (4) deterministic
    verification with rollback on failure, and (5) the store-backed
    apply boundary that re-classifies the patch before a write.
    """

    VERIFICATION_DEPTH_COMPILE = "compile"

    VERIFICATION_DEPTH_COMPILE_TESTS = "compile+tests"

    def decide(self, assessment) -> RiskDecision:

        if assessment is None:

            return self._deny(
                RiskLevel.UNKNOWN,
                "Missing risk assessment; denied.",
            )

        if not isinstance(assessment, RiskAssessment):

            return self._deny(
                RiskLevel.UNKNOWN,
                "Malformed risk assessment; denied.",
            )

        return RiskPolicy.from_level(
            assessment.risk_level,
            assessment.reason,
        )

    @staticmethod
    def from_level(level, reason="") -> RiskDecision:

        if not isinstance(level, RiskLevel):

            return RiskPolicy._deny(
                RiskLevel.UNKNOWN,
                "Missing or malformed risk level; denied.",
            )

        if level == RiskLevel.UNKNOWN:

            return RiskPolicy._deny(
                level,
                reason or (
                    "Risk could not be determined; denied."
                ),
            )

        if level == RiskLevel.LOW:

            return RiskDecision(
                risk_level=level,
                allowed=True,
                requires_human_approval=False,
                allow_auto_apply=True,
                max_attempts=3,
                verification_depth=(
                    RiskPolicy.VERIFICATION_DEPTH_COMPILE_TESTS
                ),
                reason=reason or (
                    "Low risk; automatic path allowed."
                ),
            )

        if level == RiskLevel.MEDIUM:

            return RiskDecision(
                risk_level=level,
                allowed=True,
                requires_human_approval=False,
                allow_auto_apply=True,
                max_attempts=2,
                verification_depth=(
                    RiskPolicy.VERIFICATION_DEPTH_COMPILE_TESTS
                ),
                reason=reason or (
                    "Medium risk; automatic path allowed."
                ),
            )

        if level == RiskLevel.HIGH:

            return RiskDecision(
                risk_level=level,
                allowed=True,
                requires_human_approval=True,
                allow_auto_apply=False,
                max_attempts=1,
                verification_depth=(
                    RiskPolicy.VERIFICATION_DEPTH_COMPILE_TESTS
                ),
                reason=reason or (
                    "High risk; human approval required."
                ),
            )

        return RiskDecision(
            risk_level=RiskLevel.CRITICAL,
            allowed=True,
            requires_human_approval=True,
            allow_auto_apply=False,
            max_attempts=1,
            verification_depth=(
                RiskPolicy.VERIFICATION_DEPTH_COMPILE_TESTS
            ),
            reason=reason or (
                "Critical risk; human approval required."
            ),
        )

    @staticmethod
    def _deny(level, reason) -> RiskDecision:

        return RiskDecision(
            risk_level=level,
            allowed=False,
            requires_human_approval=True,
            allow_auto_apply=False,
            max_attempts=0,
            verification_depth="",
            reason=reason,
        )
