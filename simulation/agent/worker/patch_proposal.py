from dataclasses import dataclass


@dataclass(frozen=True)
class PatchProposal:

    path: str
    action: str
    reason: str
    old_content: str
    new_content: str