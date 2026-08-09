from dataclasses import dataclass
import hashlib
import json


@dataclass(frozen=True)
class PatchProposal:

    path: str
    action: str
    reason: str
    old_content: str
    new_content: str
    allowed_paths: tuple[str, ...] = ()

    def fingerprint(self) -> str:

        data = {
            "path": self.path,
            "action": self.action,
            "reason": self.reason,
            "old_content": self.old_content,
            "new_content": self.new_content,
            "allowed_paths": self.allowed_paths,
        }

        raw = json.dumps(
            data,
            sort_keys=True,
            ensure_ascii=False
        ).encode("utf-8")

        return hashlib.sha256(raw).hexdigest()