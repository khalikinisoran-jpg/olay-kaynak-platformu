from dataclasses import dataclass


@dataclass(frozen=True)
class ControllerDecision:

    approved: bool
    reason: str