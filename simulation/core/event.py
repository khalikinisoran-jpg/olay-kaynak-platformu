from dataclasses import dataclass, field
from typing import Dict, Any
import uuid


@dataclass(frozen=True)
class Event:

    event_type: str
    payload: Dict[str, Any]
    sequence: int = 0
    event_id: str = field(
        default_factory=lambda: str(uuid.uuid4())
    )