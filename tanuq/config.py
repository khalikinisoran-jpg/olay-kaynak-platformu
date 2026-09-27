"""Tanuq user configuration.

Per-workspace config lives in ``<workspace>/.tanuq/config.json`` and
contains NO secrets. The anchor key lives outside any repository, in
``~/.tanuq/keys/``.

Tighten-only policy: the user may narrow the protection scope but can
never widen it beyond the registered workspace, and there is NO config
knob that relaxes the deterministic security core. HIGH/CRITICAL
always require human approval and UNKNOWN is always DENIED — those
rules live in ``RiskPolicy`` and are not configurable.
"""
import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from simulation.persistence.chain_anchor import generate_key_bytes

TANUQ_DIR_NAME = ".tanuq"
# Historical product name (formerly HERMES). Kept ONLY for controlled
# migration detection of pre-rename workspaces; never used as identity.
LEGACY_DIR_NAME = ".hermes"
DATA_DIR_NAME = "data"
KEYS_DIR_NAME = "keys"
CONFIG_FILE_NAME = "config.json"
PENDING_FILE_NAME = "pending_proposals.json"
EVENTS_FILE_NAME = "events.jsonl"
LEDGER_FILE_NAME = "approval_ledger.jsonl"
LEDGER_ANCHOR_FILE_NAME = "approval_ledger_anchor.jsonl"
ANCHOR_FILE_NAME = "chain_anchor.jsonl"
APPLY_JOURNAL_FILE_NAME = "apply_journal.jsonl"
DUMMY_TEST_FILE_NAME = "dummy_test.py"

VERIFICATION_DEPTHS = ("compile", "compile+tests")
DEFAULT_VERIFICATION_DEPTH = "compile+tests"
APPROVAL_TTL_SECONDS = 3600
DEFAULT_AUTHORIZER = "human-operator"


class TanuqError(Exception):
    pass


class TanuqNotInitialized(TanuqError):
    pass


@dataclass(frozen=True)
class TanuqConfig:
    workspace: str
    allowed_paths: tuple
    verification_depth: str
    created_at: str

    @property
    def workspace_path(self) -> Path:
        return Path(self.workspace).resolve()


def tanuq_home() -> Path:
    return Path.home() / ".tanuq"


def migrate_legacy_device_home() -> bool:
    """Move a pre-rename ~/.hermes device directory to ~/.tanuq.

    Controlled migration: rename-only, no deletion, no content change,
    nothing logged except the fact of the move (key material is never
    printed). Returns True when a migration was performed.
    """
    legacy = Path.home() / LEGACY_DIR_NAME
    new = tanuq_home()
    if legacy.exists() and not new.exists():
        shutil.move(str(legacy), str(new))
        return True
    return False


def migrate_legacy_workspace_dir(workspace: Path) -> bool:
    """Move a pre-rename <workspace>/.hermes directory to .tanuq."""
    legacy = Path(workspace) / LEGACY_DIR_NAME
    new = workspace / TANUQ_DIR_NAME
    if legacy.exists() and not new.exists():
        shutil.move(str(legacy), str(new))
        return True
    return False


def tanuq_dir(workspace: Path) -> Path:
    return workspace / TANUQ_DIR_NAME


def tanuq_data_dir(workspace: Path) -> Path:
    return tanuq_dir(workspace) / DATA_DIR_NAME


def config_path(workspace: Path) -> Path:
    return tanuq_dir(workspace) / CONFIG_FILE_NAME


def pending_path(workspace: Path) -> Path:
    return tanuq_data_dir(workspace) / PENDING_FILE_NAME


def key_path_for(workspace: Path) -> Path:
    resolved = Path(workspace).resolve()
    slug = hashlib.sha256(str(resolved).encode("utf-8")).hexdigest()[:16]
    return tanuq_home() / KEYS_DIR_NAME / f"ws-{slug}.key"


def is_initialized(workspace: Path) -> bool:
    return config_path(workspace).exists()


def resolve_workspace(raw=None) -> Path:
    base = Path(raw) if raw else Path.cwd()
    try:
        resolved = base.expanduser().resolve()
    except Exception as exc:
        raise TanuqError(f"Workspace path could not be resolved: {exc}")
    if not resolved.exists():
        raise TanuqError(f"Workspace does not exist: {resolved}")
    if not resolved.is_dir():
        raise TanuqError(f"Workspace is not a directory: {resolved}")
    return resolved


def validate_config_values(workspace: Path, allowed_paths, verification_depth) -> tuple:
    ws = Path(workspace).resolve()
    if verification_depth not in VERIFICATION_DEPTHS:
        raise TanuqError(
            "verification_depth must be one of "
            f"{list(VERIFICATION_DEPTHS)}; got {verification_depth!r}"
        )
    cleaned = []
    for raw in allowed_paths:
        try:
            resolved = Path(raw).expanduser().resolve()
        except Exception as exc:
            raise TanuqError(f"Allowed path could not be resolved: {raw!r} ({exc})")
        if not resolved.exists():
            raise TanuqError(f"Allowed path does not exist: {resolved}")
        if resolved != ws and not resolved.is_relative_to(ws):
            raise TanuqError(
                "Tighten-only policy: allowed paths must be inside the "
                f"workspace {ws}; got {resolved}"
            )
        cleaned.append(str(resolved))
    if not cleaned:
        cleaned = [str(ws)]
    return tuple(dict.fromkeys(cleaned)), verification_depth


def save_config(config: TanuqConfig) -> None:
    path = config_path(config.workspace_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "workspace": config.workspace,
        "allowed_paths": list(config.allowed_paths),
        "verification_depth": config.verification_depth,
        "created_at": config.created_at,
        "defaults": {
            "governed": True,
            "anchored_evidence": True,
            "approval_ttl_seconds": APPROVAL_TTL_SECONDS,
            "high_critical": "approval required (not configurable)",
            "unknown": "deny (not configurable)",
        },
    }
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def load_config(workspace: Path) -> TanuqConfig:
    migrate_legacy_workspace_dir(Path(workspace))
    path = config_path(workspace)
    if not path.exists():
        raise TanuqNotInitialized(
            f"Tanuq is not initialized in {workspace}. "
            "Run: tanuq init"
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise TanuqError(f"Tanuq config is corrupted ({path}): {exc}")
    try:
        allowed = tuple(payload["allowed_paths"])
        depth = payload["verification_depth"]
    except (KeyError, TypeError) as exc:
        raise TanuqError(f"Tanuq config is missing required fields: {exc}")
    allowed_paths, verification_depth = validate_config_values(
        workspace, allowed, depth
    )
    return TanuqConfig(
        workspace=str(Path(workspace).resolve()),
        allowed_paths=allowed_paths,
        verification_depth=verification_depth,
        created_at=str(payload.get("created_at", "")),
    )


def _write_key_file(path: Path, key: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    tmp = path.with_suffix(".tmp")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        os.write(fd, key)
        os.fsync(fd)
    finally:
        os.close(fd)
    tmp.replace(path)


def ensure_anchor_key(workspace: Path) -> Path:
    path = key_path_for(workspace)
    if not path.exists():
        _write_key_file(path, generate_key_bytes().encode("utf-8"))
    return path


def read_anchor_key(workspace: Path) -> bytes:
    path = key_path_for(workspace)
    if not path.exists():
        raise TanuqError(
            f"Anchor key file is missing: {path}. Without the key the "
            "anchored evidence cannot be verified (fail-closed)."
        )
    key = path.read_bytes().strip()
    if len(key) < 32:
        raise TanuqError(
            f"Anchor key file {path} is too short (<32 bytes); refusing "
            "to run fail-closed."
        )
    return key


TOKEN_FILE_NAME = "token"


def token_path() -> Path:
    return tanuq_home() / TOKEN_FILE_NAME


def ensure_local_token() -> str:
    path = token_path()
    if path.exists():
        token = path.read_text(encoding="utf-8").strip()
        if len(token) >= 16:
            return token
        path.unlink()
    import secrets
    token = secrets.token_urlsafe(32)
    _write_key_file(path, token.encode("utf-8"))
    return token


def read_local_token():
    path = token_path()
    if not path.exists():
        return None
    token = path.read_text(encoding="utf-8").strip()
    return token or None


def init_workspace(
    workspace: Path,
    allowed_paths=None,
    verification_depth=DEFAULT_VERIFICATION_DEPTH,
) -> TanuqConfig:
    migrate_legacy_device_home()
    ws = resolve_workspace(workspace)
    migrate_legacy_workspace_dir(ws)
    allowed_paths, verification_depth = validate_config_values(
        ws,
        allowed_paths if allowed_paths else (str(ws),),
        verification_depth,
    )
    ensure_anchor_key(ws)
    ensure_local_token()
    config = TanuqConfig(
        workspace=str(ws),
        allowed_paths=allowed_paths,
        verification_depth=verification_depth,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    save_config(config)
    tanuq_data_dir(ws).mkdir(parents=True, exist_ok=True)
    return config


WORKSPACES_FILE_NAME = "workspaces.json"


def register_workspace(workspace: Path) -> None:
    """Record the workspace in the device-level registry (no secrets)."""
    path = tanuq_home() / WORKSPACES_FILE_NAME
    entries = []
    if path.exists():
        try:
            entries = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(entries, list):
                entries = []
        except Exception:
            entries = []
    resolved = str(Path(workspace).resolve())
    entries = [e for e in entries if e.get("path") != resolved]
    entries.append({"path": resolved, "registered_at": now_iso()})
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)


def list_registered_workspaces():
    path = tanuq_home() / WORKSPACES_FILE_NAME
    if not path.exists():
        return []
    try:
        entries = json.loads(path.read_text(encoding="utf-8"))
        return entries if isinstance(entries, list) else []
    except Exception:
        return []


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Anonymous usage telemetry preference (user level) - FAZ 2.1
# ---------------------------------------------------------------------------
# This is a USER PREFERENCE, never a governance knob: it can only stop a
# future telemetry transport from running. It cannot relax any security
# rule (risk / policy / approval / apply / verify are untouched here).

USAGE_ENV_VAR = "TANUQ_USAGE"
USAGE_ENDPOINT_ENV_VAR = "TANUQ_USAGE_ENDPOINT"
USER_CONFIG_FILE_NAME = "config.json"  # at ~/.tanuq/ (NOT the workspace one)
_USAGE_TRUE = frozenset({"on", "true", "1", "yes"})
_USAGE_FALSE = frozenset({"off", "false", "0", "no"})


def user_config_path() -> Path:
    """User-level preference file: ``~/.tanuq/config.json``.

    Deliberately NOT the workspace config: one preference must apply to
    every workspace of this user.
    """
    return tanuq_home() / USER_CONFIG_FILE_NAME


def _read_user_config(config_path=None) -> dict:
    path = Path(config_path) if config_path is not None else user_config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def read_usage_remote_preference(env=None, config_path=None):
    """Resolve the telemetry preference: valid ENV > user config > ON.

    Returns ``(enabled, source)`` with ``source`` in
    ``{"env", "config", "default"}``.

    Deterministic contract (FAZ 2.1):
    - a valid env value (on/true/1/yes | off/false/0/no, case-insensitive,
      trimmed) wins over everything;
    - an INVALID env value is ignored (treated as unset) so a typo can
      never silently override an explicit user config choice;
    - the config file is honored only when ``usage_remote`` is a real
      boolean; corrupt/missing config falls back to the default;
    - no setting at all -> DEFAULT = ON.
    """
    environ = os.environ if env is None else env
    raw = environ.get(USAGE_ENV_VAR)
    if isinstance(raw, str):
        value = raw.strip().lower()
        if value in _USAGE_TRUE:
            return True, "env"
        if value in _USAGE_FALSE:
            return False, "env"
        # invalid value: fall through (deterministic)
    flag = _read_user_config(config_path).get("usage_remote")
    if isinstance(flag, bool):
        return flag, "config"
    return True, "default"


def is_usage_endpoint_configured(env=None, config_path=None) -> bool:
    """Presence check only — the value is never returned or printed."""
    environ = os.environ if env is None else env
    raw = environ.get(USAGE_ENDPOINT_ENV_VAR)
    if isinstance(raw, str) and raw.strip():
        return True
    endpoint = _read_user_config(config_path).get("usage_endpoint")
    return isinstance(endpoint, str) and bool(endpoint.strip())


def write_usage_remote_preference(enabled: bool, config_path=None):
    """Persist the user-level preference (atomic read-modify-write).

    Creates ``~/.tanuq/config.json`` on first explicit write; preserves
    unrelated existing keys; stores ONLY a boolean.
    """
    path = Path(config_path) if config_path is not None else user_config_path()
    data = _read_user_config(path)
    data["usage_remote"] = bool(enabled)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
    return bool(enabled), "config"
