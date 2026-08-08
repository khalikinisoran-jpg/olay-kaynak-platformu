from dataclasses import dataclass


@dataclass(frozen=True)
class ApplyResult:

    success: bool
    path: str
    message: str