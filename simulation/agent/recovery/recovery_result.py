from dataclasses import dataclass, field

from simulation.agent.recovery.recovery_attempt import (
    RecoveryAttempt
)


@dataclass(frozen=True)
class RecoveryResult:

    """Deterministic evidence contract produced by the recovery loop.

    The result is not a bare boolean. It carries the full bounded
    decision: terminal status, how many attempts were consumed, the
    enforced cap, the append-only attempt history, the final apply
    and verification outcomes and the failure reason.
    """

    terminal_status: str
    attempts_used: int
    max_attempts: int
    attempt_history: tuple[RecoveryAttempt, ...] = field(
        default_factory=tuple
    )
    failure_reason: str = ""
    failure_stage: str = ""

    @property
    def success(self) -> bool:

        return self.terminal_status == "SUCCESS"

    @property
    def terminal_failure(self) -> bool:

        return self.terminal_status == "TERMINAL_FAILURE"

    @property
    def retry_count(self) -> int:

        return max(
            0,
            self.attempts_used - 1
        )

    @property
    def final_attempt(self) -> RecoveryAttempt | None:

        if not self.attempt_history:

            return None

        return self.attempt_history[-1]

    @property
    def verification_evidence(self):

        final = self.final_attempt

        if final is None:

            return ()

        return final.evidence

    @property
    def final_apply_result(self):

        final = self.final_attempt

        if final is None:

            return None

        return final.apply_result

    @property
    def final_verification_result(self):

        final = self.final_attempt

        if final is None:

            return None

        return final.verification

    @property
    def final_apply_success(self):

        final = self.final_attempt

        if final is None:

            return False

        return final.apply_success

    @property
    def final_verification_passed(self):

        final = self.final_attempt

        if final is None:

            return False

        return final.verification_passed
