from dataclasses import dataclass, field


@dataclass(frozen=True)
class ApplyResult:

    success: bool
    path: str
    message: str
    intent_id: str = field(
        default=""
    )
