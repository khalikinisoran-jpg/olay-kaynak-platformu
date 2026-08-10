from dataclasses import dataclass


PASS = "PASS"
FAIL = "FAIL"


@dataclass(frozen=True)
class VerificationEvidence:

    stage: str
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    error: str = ""


@dataclass(frozen=True)
class VerificationResult:

    status: str
    exit_code: int
    stdout: str
    stderr: str
    command: tuple[str, ...]
    evidence: tuple[VerificationEvidence, ...] = ()
    failure_reason: str = ""

    @property
    def passed(self) -> bool:

        return self.status == PASS

    @property
    def failed(self) -> bool:

        return not self.passed
