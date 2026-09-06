"""Pending proposal store for the Tanuq product flow.

Same JSON schema as the existing governed CLI pending-parity mechanism
(``agent_run._cli_save_pending``): exact PatchProposal fields plus the
computed fingerprint. This file is a convenience store, NOT an
approval authority; approval still binds to the exact fingerprint via
``ApprovalStore``.

Multi-process safety: read-modify-write cycles (save/remove) are
serialized with the existing core ``_ProcessFileLock`` primitive (the
same OS-level lock used by the event store and approval ledger). Two
agents proposing at the same time can never lose a pending record.
"""
import json
from pathlib import Path

from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.persistence.process_lock import _ProcessFileLock

from tanuq.config import pending_path, now_iso

PENDING_LOCK_TIMEOUT = 10.0


class PendingError(Exception):
    pass


def _record(patch, session=None) -> dict:
    record = {
        "path": patch.path,
        "action": patch.action,
        "reason": patch.reason,
        "old_content": patch.old_content,
        "new_content": patch.new_content,
        "allowed_paths": list(patch.allowed_paths),
        "fingerprint": patch.fingerprint(),
        "created_at": now_iso(),
    }
    if session:
        record["session"] = str(session)
    return record


def save_pending(workspace: Path, patches, session=None) -> int:
    path = pending_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    new_records = [_record(p, session=session) for p in patches]
    with _ProcessFileLock(path, timeout=PENDING_LOCK_TIMEOUT):
        existing = _read_records(path)
        drop = [r for r in existing if r in new_records]
        data = [r for r in existing if r not in new_records] + new_records
        _atomic_write(path, data)
    return len(patches)


def load_pending(workspace: Path):
    path = pending_path(workspace)
    if not path.exists():
        return []
    try:
        return _read_records(path)
    except PendingError:
        raise
    except Exception as exc:
        raise PendingError(
            f"Pending proposals file is corrupted ({path}): {exc}"
        )


def remove_pending(workspace: Path, fingerprints) -> int:
    drop = set(fingerprints)
    path = pending_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    with _ProcessFileLock(path, timeout=PENDING_LOCK_TIMEOUT):
        records = _read_records(path)
        remaining = [
            r for r in records if r.get("fingerprint") not in drop
        ]
        removed = len(records) - len(remaining)
        _atomic_write(path, remaining)
    return removed


def _read_records(path: Path):
    if not path.exists():
        return []
    try:
        raw = path.read_text(encoding="utf-8")
        if not raw.strip():
            return []
        data = json.loads(raw)
        if not isinstance(data, list):
            return []
        return data
    except Exception as exc:
        raise PendingError(
            f"Pending proposals file is corrupted ({path}): {exc}"
        )


def _atomic_write(path: Path, data) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def patch_from_record(record: dict) -> PatchProposal:
    return PatchProposal(
        path=record["path"],
        action=record.get("action", "modify"),
        reason=record.get("reason", "tanuq propose"),
        old_content=record["old_content"],
        new_content=record["new_content"],
        allowed_paths=tuple(record.get("allowed_paths", ())),
    )
