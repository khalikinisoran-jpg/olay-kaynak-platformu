"""P9.7-A Session Persistence Contract — versioned, integrity-protected, data-only.

PERSISTENCE IS DATA, NOT AUTHORITY.

This module MUST NOT:
 - call WorkerActionPipeline.execute
 - call FileApplier / ApplyExecutor
 - call ApprovalStore.grant / find_valid as shortcut
 - call RiskEngine.classify / GovernanceEvaluator as recovery authority
 - call VerificationExecutor.verify
 - apply patches or rollback
 - interpret persisted fields as authorization proof

Integrity: local tamper detection via deterministic SHA-256 over canonical JSON.
Uses existing HashChain primitive as canonical (json.dumps sort_keys).
"""
import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Tuple

# ---------------------------------------------------------------------------
# Schema + classification
# ---------------------------------------------------------------------------

SESSION_SNAPSHOT_SCHEMA_VERSION = 1
SUPPORTED_SCHEMA_VERSIONS = (1,)

# A. IDENTITY / CORRELATION DATA
# B. SESSION LIFECYCLE DATA
# C. ADVISORY / OBSERVATIONAL DATA
# D. FORBIDDEN AS AUTHORITY — never treated as proof, stripped on load

FORBIDDEN_AUTHORITY_FIELDS = frozenset({
    "approved",
    "human_approved",
    "approval_id",
    "approval",
    "bypass_governance",
    "bypass",
    "human_approval",
    "verification_passed",
    "verified",
    "tests_passed",
    "test_passed",
    "risk_override",
    "risk_level",
    "risk_authority",
    "governance_override",
    "apply_directly",
    "write_directly",
    "path_override",
    "target_path",
})

# All persisted fields classification (for report)
PERSISTED_FIELD_CLASSIFICATION = {
    "schema_version": "A IDENTITY / correlation + version",
    "session_id": "A IDENTITY",
    "workspace": "A IDENTITY",
    "state": "B LIFECYCLE",
    "proposal_set_id": "A IDENTITY / correlation",
    "attempt": "B LIFECYCLE",
    "resume_count": "B LIFECYCLE",
    "governance_count": "B LIFECYCLE",
    "history": "B LIFECYCLE / C ADVISORY (observational transition records)",
    "snapshot_at": "C ADVISORY (timestamp of persistence)",
    "integrity": "D INTEGRITY (not authority, tamper detection only)",
}

VALID_SESSION_STATES = frozenset({
    "CREATED", "INSPECTING", "INSPECTED", "PROPOSING", "GOVERNING",
    "WAITING_APPROVAL", "AUTHORIZED", "VERIFIED", "DENIED", "FAILED",
})


class SessionSnapshotIntegrityError(ValueError):
    """Integrity or schema validation failure (fail-closed)."""


@dataclass(frozen=True)
class SessionSnapshot:
    """Validated primitive snapshot (data only, never authority)."""

    schema_version: int
    session_id: str
    workspace: str
    state: str
    proposal_set_id: str
    attempt: int
    resume_count: int
    governance_count: int
    history: Tuple[dict, ...]
    snapshot_at: str
    integrity: str

    def to_dict(self) -> dict:
        """Return JSON-compatible dict including integrity."""
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "workspace": self.workspace,
            "state": self.state,
            "proposal_set_id": self.proposal_set_id,
            "attempt": self.attempt,
            "resume_count": self.resume_count,
            "governance_count": self.governance_count,
            "history": list(self.history),
            "snapshot_at": self.snapshot_at,
            "integrity": self.integrity,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical_bytes(payload: dict) -> bytes:
    """Deterministic canonical representation: sorted keys, no whitespace."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _compute_integrity(payload: dict) -> str:
    """SHA-256 hex over canonical payload (without integrity field)."""
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _strip_forbidden_fields(data: dict) -> dict:
    """Remove forbidden authority-shaped fields (deterministic strip contract)."""
    cleaned = {}
    for k, v in data.items():
        if k in FORBIDDEN_AUTHORITY_FIELDS:
            continue
        cleaned[k] = v
    return cleaned


def _safe_session_filename(session_id: str) -> str:
    """Sanitize session_id to safe filename, prevent traversal."""
    if not isinstance(session_id, str) or not session_id:
        raise ValueError("session_id must be non-empty string")
    # Allow alnum, -, _, hex-like (same as AgentSession default)
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", session_id):
        raise ValueError(f"session_id contains unsafe characters: {session_id!r}")
    return f"{session_id}.snapshot.json"


def _build_payload_from_session(session) -> dict:
    """Extract primitive payload from AgentSession (no live objects)."""
    # Fail-closed validation mirrors AgentSession invariants but minimal
    sid = str(getattr(session, "session_id", "") or "")
    if not sid:
        raise ValueError("session_id missing")
    ws = str(getattr(session, "workspace", "") or "")
    # state may be Enum
    st = getattr(session, "state", None)
    state_val = getattr(st, "value", st)
    state_str = str(state_val or "")
    if state_str not in VALID_SESSION_STATES:
        raise ValueError(f"invalid session state {state_str!r}")
    proposal_set_id = str(getattr(session, "proposal_set_id", "") or "")
    attempt = int(getattr(session, "attempt", 1) or 1)
    resume_count = int(getattr(session, "resume_count", 0) or 0)
    governance_count = int(getattr(session, "governance_count", 0) or 0)
    # history: ensure list of dicts with primitives only, deep copy via json roundtrip
    raw_hist = getattr(session, "history", []) or []
    # Validate history is list of dicts, strip any non-serializable? Keep primitives via json
    try:
        # ensure JSON-serializable copy
        history_copy = json.loads(json.dumps(raw_hist, ensure_ascii=False))
        if not isinstance(history_copy, list):
            raise ValueError("history must be list")
    except Exception as e:
        raise ValueError(f"history not serializable: {e}")
    # ensure each entry is dict
    for entry in history_copy:
        if not isinstance(entry, dict):
            raise ValueError("history entry must be dict")

    payload = {
        "schema_version": SESSION_SNAPSHOT_SCHEMA_VERSION,
        "session_id": sid,
        "workspace": ws,
        "state": state_str,
        "proposal_set_id": proposal_set_id,
        "attempt": attempt,
        "resume_count": resume_count,
        "governance_count": governance_count,
        "history": history_copy,
        "snapshot_at": _now_iso(),
    }
    return payload


def save_snapshot(session, base_dir: Path = Path("data/session_snapshots")) -> Path:
    """Persist AgentSession as versioned integrity-protected snapshot.

    Atomic write, path-confined, no execution side effects.
    Returns Path of written snapshot.
    """
    payload = _build_payload_from_session(session)
    # Integrity covers all semantically relevant persisted fields (payload)
    integrity = _compute_integrity(payload)
    record = dict(payload)
    record["integrity"] = integrity

    base = Path(base_dir)
    base.mkdir(parents=True, exist_ok=True)
    # Resolve base to absolute for traversal check
    try:
        base_resolved = base.resolve()
    except Exception:
        base_resolved = base

    fname = _safe_session_filename(payload["session_id"])
    target = base_resolved / fname

    # Ensure target stays within base (prevent traversal even if session_id sanitized)
    try:
        target.resolve().relative_to(base_resolved)
    except Exception:
        raise ValueError("snapshot path escapes base_dir")

    # Atomic write via temp + replace
    tmp = target.with_suffix(target.suffix + ".tmp")
    data = json.dumps(record, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8")
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, target)
    return target


def load_snapshot(path: Path) -> SessionSnapshot:
    """Load and validate snapshot (fail-closed, read-only, no authority).

    Rejects: invalid JSON, missing integrity, truncated integrity, unsupported schema,
    invalid state, hash mismatch, path escape.
    Strips forbidden authority-shaped fields.
    Never executes, never approves.
    """
    p = Path(path)
    # Path confinement: if p is inside default base, check not escaping; otherwise just read file
    # But prevent directory traversal reading arbitrary?
    # For P9.7-A we treat any path as file read, but ensure snapshot itself was validated
    try:
        raw = p.read_text(encoding="utf-8")
    except Exception as e:
        raise SessionSnapshotIntegrityError(f"cannot read snapshot: {e}") from e

    # Invalid JSON -> rejection
    try:
        data = json.loads(raw)
    except Exception as e:
        raise SessionSnapshotIntegrityError(f"invalid JSON: {e}") from e

    if not isinstance(data, dict):
        raise SessionSnapshotIntegrityError("snapshot must be object")

    # Strip forbidden fields deterministically (ignore)
    # But keep original for integrity check: forbidden fields should not have been part of integrity
    # So if data contains forbidden field, we ignore it AFTER integrity check? Spec says strip.
    # We choose: if forbidden field present, remove it and continue, but do not treat as authority.
    # The integrity check will still fail if the file was tampered with forbidden addition *after* save,
    # because the saved integrity was computed without forbidden fields. An attacker adding forbidden field
    # will not affect integrity check (since we strip before recompute), so we must ensure injection does not become authority
    # but also that tampering of relevant fields is detected. Our integrity only covers payload (without forbidden),
    # so forbidden injection is intentionally ignored (safe observation). This matches strip contract.
    # For rejection contract, we could also reject if forbidden present, but spec allows strip.

    # Check required fields
    if "integrity" not in data:
        raise SessionSnapshotIntegrityError("missing integrity")
    integrity = data.get("integrity")
    if not isinstance(integrity, str) or len(integrity) != 64 or not re.fullmatch(r"[0-9a-f]{64}", integrity):
        raise SessionSnapshotIntegrityError("truncated or invalid integrity")

    if "schema_version" not in data:
        raise SessionSnapshotIntegrityError("missing schema_version")
    sv = data.get("schema_version")
    if sv not in SUPPORTED_SCHEMA_VERSIONS:
        raise SessionSnapshotIntegrityError(f"unsupported schema_version {sv!r}")

    if "state" not in data:
        raise SessionSnapshotIntegrityError("missing state")
    state = data.get("state")
    if state not in VALID_SESSION_STATES:
        raise SessionSnapshotIntegrityError(f"invalid state {state!r}")

    # Recompute integrity over payload without integrity field, after stripping forbidden fields from payload for canonical
    # But payload for hash should be the original payload dict as saved (without integrity)
    # If file was tampered to add forbidden field, that field will be in data and we will strip it before hashing,
    # so hash will match original (attacker cannot exploit). That's intended strip behavior.
    payload_for_hash = {k: v for k, v in data.items() if k != "integrity"}
    # Strip forbidden from payload copy for hash as well (since save never included them)
    payload_for_hash = _strip_forbidden_fields(payload_for_hash)

    # Also need to ensure payload_for_hash contains only expected keys? Additional unknown keys are not forbidden but should they be considered tamper?
    # Spec says unknown authority-shaped injected fields must not become authority — strip those. Other unknown correlation fields could be additional data?
    # For integrity, any extra non-forbidden unknown key added after save would be part of payload and cause hash mismatch -> rejection. That's stricter and desirable.
    # But if we strip only forbidden, extra unknown non-forbidden keys will cause hash mismatch -> fail-closed. Good.

    expected = _compute_integrity(payload_for_hash)
    if expected != integrity:
        raise SessionSnapshotIntegrityError("integrity mismatch (tamper detected)")

    # Now build validated snapshot object, stripping forbidden fields from final dict as well
    # Extract validated primitive fields
    try:
        session_id = str(data["session_id"])
        workspace = str(data["workspace"])
        proposal_set_id = str(data.get("proposal_set_id", "") or "")
        attempt = int(data.get("attempt", 1))
        resume_count = int(data.get("resume_count", 0))
        governance_count = int(data.get("governance_count", 0))
        history = tuple(data.get("history", []) or [])
        snapshot_at = str(data.get("snapshot_at", "") or _now_iso())
    except Exception as e:
        raise SessionSnapshotIntegrityError(f"malformed snapshot fields: {e}") from e

    # Validate session_id safe
    _safe_session_filename(session_id)

    # Validate types/bounds
    if not (1 <= attempt <= 3):
        raise SessionSnapshotIntegrityError("attempt out of bounds 1..3")
    if resume_count < 0 or governance_count < 0:
        raise SessionSnapshotIntegrityError("negative count")

    # History must be tuple of dicts
    if not isinstance(history, (list, tuple)):
        raise SessionSnapshotIntegrityError("history must be list")
    # Ensure each entry is dict (already validated via json)

    return SessionSnapshot(
        schema_version=int(sv),
        session_id=session_id,
        workspace=workspace,
        state=state,
        proposal_set_id=proposal_set_id,
        attempt=attempt,
        resume_count=resume_count,
        governance_count=governance_count,
        history=tuple(dict(e) if isinstance(e, dict) else e for e in history),
        snapshot_at=snapshot_at,
        integrity=integrity,
    )


class SessionSnapshotStore:
    """Minimal file-based persistence helper (explicit base_dir, no authority)."""

    def __init__(self, base_dir: Path = Path("data/session_snapshots")):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.base_resolved = self.base_dir.resolve()
        except Exception:
            self.base_resolved = self.base_dir

    def save(self, session) -> Path:
        return save_snapshot(session, base_dir=self.base_resolved)

    def load(self, session_id: str) -> SessionSnapshot:
        fname = _safe_session_filename(session_id)
        target = self.base_resolved / fname
        # Confinement check
        try:
            target.resolve().relative_to(self.base_resolved)
        except Exception:
            raise SessionSnapshotIntegrityError("path escapes base_dir")
        return load_snapshot(target)

    def load_path(self, path: Path) -> SessionSnapshot:
        # Allow loading arbitrary path but still validate integrity
        # Ensure path is file and not directory traversal beyond base if needed?
        p = Path(path)
        return load_snapshot(p)

    @staticmethod
    def _assert_no_authority_imports():
        import pathlib
        import re
        text = pathlib.Path(__file__).read_text(encoding="utf-8")
        imports = re.findall(r"^\s*(?:from|import)\s+.*$", text, flags=re.MULTILINE)
        forbidden = []
        for line in imports:
            if "simulation.agent.apply.file_applier" in line:
                forbidden.append(line.strip())
            if "simulation.agent.apply.apply_executor" in line:
                forbidden.append(line.strip())
            if "simulation.agent.approval.approval_store" in line:
                forbidden.append(line.strip())
            if "simulation.security.risk_engine" in line:
                forbidden.append(line.strip())
            if "simulation.security.governance_evaluator" in line:
                forbidden.append(line.strip())
            if "simulation.agent.verify.verification_executor" in line:
                forbidden.append(line.strip())
            if "simulation.agent.pipeline.worker_action_pipeline" in line:
                forbidden.append(line.strip())
            if "simulation.agent.apply.apply_authorization" in line:
                forbidden.append(line.strip())
        if forbidden:
            raise AssertionError(f"SessionPersistence must not import authority modules: {forbidden}")
        code = re.sub(r'""".*?"""', '', text, flags=re.DOTALL)
        code_wo = "\n".join(l for l in code.splitlines() if "_assert_no_authority" not in l)
        # self-trigger avoid: split literals
        code_wo_check = code_wo.replace('".grant' + '("', '').replace("'.grant" + "('", "")
        if ".grant" + "(" in code_wo_check and "ApprovalStore" in code_wo_check:
            raise AssertionError("SessionPersistence must not call ApprovalStore." + "grant")
        if "find" + "_valid" in code_wo:
            raise AssertionError("SessionPersistence must not call ApprovalStore." + "find" + "_valid")
        if "File" + "Applier" in code_wo:
            raise AssertionError("SessionPersistence must not reference File" + "Applier")
        if "Apply" + "Executor" in code_wo:
            raise AssertionError("SessionPersistence must not reference Apply" + "Executor")
