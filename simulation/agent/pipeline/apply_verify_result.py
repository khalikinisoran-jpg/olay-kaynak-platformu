from dataclasses import dataclass

from simulation.agent.apply.apply_result import (
    ApplyResult
)

from simulation.agent.verify.verification_result import (
    VerificationEvidence,
    VerificationResult,
)


@dataclass(frozen=True)
class ApplyVerifyResult:

    apply_result: ApplyResult
    verification: VerificationResult | None
    success: bool
    verification_ran: bool

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
