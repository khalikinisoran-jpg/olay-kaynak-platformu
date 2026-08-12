from dataclasses import dataclass

from simulation.agent.apply.apply_result import (
    ApplyResult
)

from simulation.agent.verify.verification_result import (
    VerificationEvidence,
    VerificationResult,
)


@dataclass(frozen=True)
class RollbackResult:

    """Outcome of a bounded rollback after a failed verification.

    ``success`` is True only when the pre-apply content was restored
    and the read-back confirmed it. ``restore_verified`` records that
    the read-back check passed. ``clean_verified`` records whether the
    restored (pre-apply) state itself passed a deterministic
    compile-only verification, when one was run. ``clean_verification``
    carries the optional clean-state verification result.
    """

    success: bool
    path: str
    message: str
    restore_verified: bool = False
    clean_verified: bool = False
    clean_verification: VerificationResult | None = None


@dataclass(frozen=True)
class ApplyVerifyResult:

    apply_result: ApplyResult
    verification: VerificationResult | None
    success: bool
    verification_ran: bool
    rollback: RollbackResult | None = None

    @property
    def apply_success(self) -> bool:

        return self.apply_result.success

    @property
    def verification_passed(self) -> bool:

        return bool(
            self.verification is not None
            and self.verification.passed
        )

    @property
    def exit_code(self) -> int:

        if self.verification is not None:

            return self.verification.exit_code

        return (
            0
            if self.apply_result.success
            else -1
        )

    @property
    def stdout(self) -> str:

        if self.verification is None:

            return ""

        return self.verification.stdout

    @property
    def stderr(self) -> str:

        if self.verification is None:

            return ""

        return self.verification.stderr

    @property
    def evidence(self) -> tuple[VerificationEvidence, ...]:

        if self.verification is None:

            return ()

        return self.verification.evidence

    @property
    def failure_reason(self) -> str:

        if self.verification is not None:

            return self.verification.failure_reason

        if self.apply_result.success:

            return ""

        return self.apply_result.message
