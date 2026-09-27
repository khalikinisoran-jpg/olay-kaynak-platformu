"""TANUQ Usage Signal V1 â€” local, read-only derivation (FAZ 1).

FAZ 1 scope: derive anonymous usage signals from the records TANUQ
already writes. Remote transport / dashboard / endpoint = FAZ 2 (not
implemented here).

Contract (hard rules):
- Reads ONLY existing local records: EventStore ``events.jsonl``,
  ApplyOutcomeJournal ``apply_journal.jsonl`` and ``TanuqConfig``
  (``created_at``). The ApprovalLedger uses the same JSONL shape and is
  supported by the generic reader, but no V1 signal is derived from it
  (the schema has no approval event yet).
- ``simulation/**`` never imports this module; the governance pipeline
  never calls it. Import direction is tanuq -> simulation only.
- Usage Signal can NEVER influence ALLOW/DENY/REVIEW/UNKNOWN or any
  governance decision: it is a post-hoc, side-effect-free projection.
- Fail-silent: any error (missing/corrupt files, permission, HMAC,
  disk write) returns without raising, without touching stdout/stderr,
  and without changing any exit code.
- stdlib only (hmac/hashlib/json/os/secrets/sys/uuid/datetime/pathlib).
  The usage HMAC secret is generated with isolated ``secrets`` (NOT the
  chain-anchor key machinery): the usage-id lifecycle must stay
  independent from governance key material (rotation/reset must never
  touch anchor keys).
- Privacy: signal payloads carry only aggregate enums (risk level,
  decision class, terminal state, error class). NEVER path, filename,
  content, diff, reason, fingerprint, task_id, approval_id, intent_id,
  prompt, LLM output, repo/username/email, secrets, stdout/stderr,
  traceback or raw error messages. Governance identifiers are used
  only as local HMAC grouping keys: never persisted raw, never emitted.

Public API:
    collect_usage_signals(environment=None, *, workspace=None,
                          usage_dir=None, secret_path=None, persist=True)
    record_usage_error(error_class, *, environment=None, workspace=None,
                       usage_dir=None, secret_path=None, persist=True)
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from tanuq import __version__
from tanuq.config import (
    APPLY_JOURNAL_FILE_NAME,
    EVENTS_FILE_NAME,
    KEYS_DIR_NAME,
    tanuq_home,
)

SCHEMA_VERSION = 1

USAGE_EVENTS = frozenset([
    "first_run",
    "run_started",
    "decision_allow",
    "decision_review",
    "decision_deny",
    "decision_unknown",
    "apply_success",
    "apply_failure",
    "verify_success",
    "verify_failure",
    "run_completed",
    "error",
])

RISK_VALUES = frozenset({"UNKNOWN", "LOW", "MEDIUM", "HIGH", "CRITICAL"})
DECISION_CLASSES = frozenset({"allow", "review", "deny", "unknown"})
TERMINAL_STATES = frozenset(
    {"verified", "apply_failed", "rolled_back", "rollback_failed"}
)
OS_FAMILIES = frozenset({"windows", "linux", "macos", "other"})
SIGNAL_KEYS = frozenset({
    "schema_version", "event", "timestamp", "version", "os_family",
    "install_id", "run_id", "risk_level", "decision_class",
    "terminal_state", "error_class",
})

_RUN_KEY_CAP = 10000
_EMITTED_CAP = 20000
_INSTALL_ID_HEX_LEN = 32
_RUN_KEY_HEX_LEN = 16


# ---------------------------------------------------------------------------
# anonymization
# ---------------------------------------------------------------------------

def load_usage_secret(secret_path=None) -> bytes:
    """Load or create the isolated usage HMAC secret (32 bytes, hex).

    Location follows the existing local-key convention
    (``~/.tanuq/keys/``) but uses its OWN file (``usage.key``) so usage
    identifiers can be rotated without touching governance key material.
    """
    path = Path(secret_path) if secret_path else (
        tanuq_home() / KEYS_DIR_NAME / "usage.key"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        text = path.read_text(encoding="utf-8").strip()
        if len(text) >= 32:
            return text.encode("utf-8")
    raw = secrets.token_hex(32)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    try:
        fd = os.open(str(path), flags, 0o600)
    except FileExistsError:
        return path.read_text(encoding="utf-8").strip().encode("utf-8")
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(raw)
    return raw.encode("utf-8")


def make_install_id(workspace, secret: bytes) -> str:
    """Stable anonymous workspace identifier.

    HMAC-SHA256(secret, canonical workspace path), truncated. The path
    itself is never stored in any signal and the id is not reversible
    without the local secret (which never leaves ``~/.tanuq``).
    """
    canonical = str(Path(workspace).expanduser().resolve())
    digest = hmac.new(secret, canonical.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:_INSTALL_ID_HEX_LEN]


def _run_key(secret: bytes, raw_identity: str) -> str:
    """Local-only grouping key (never emitted, never persisted raw)."""
    digest = hmac.new(secret, raw_identity.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:_RUN_KEY_HEX_LEN]


def _os_family() -> str:
    platform = sys.platform
    if platform.startswith("win"):
        return "windows"
    if platform == "darwin":
        return "macos"
    if platform.startswith("linux"):
        return "linux"
    return "other"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# signal schema
# ---------------------------------------------------------------------------

def build_signal(event, *, ctx, run_id, **extra):
    if event not in USAGE_EVENTS:
        raise ValueError(f"unknown usage event: {event}")
    signal = {
        "schema_version": SCHEMA_VERSION,
        "event": event,
        "timestamp": _now(),
        "version": ctx.get("version", ""),
        "os_family": ctx.get("os_family", ""),
        "install_id": ctx.get("install_id", ""),
        "run_id": run_id,
    }
    for key, value in extra.items():
        if value is not None and value != "":
            signal[key] = value
    return signal


# ---------------------------------------------------------------------------
# reader (incremental, append-only safe)
# ---------------------------------------------------------------------------

def read_new_records(path, offset: int):
    """Read complete new JSONL records after ``offset`` bytes.

    Returns ``(records, new_offset)``. A trailing partial line (a write
    in progress or a truncated file) is never consumed: the offset only
    advances past complete lines, so the next scan retries it. Malformed
    input never raises out of this function.
    """
    path = Path(path)
    offset = max(int(offset or 0), 0)
    if not path.exists():
        return [], offset
    size = path.stat().st_size
    if size < offset:
        offset = 0  # file replaced/truncated â€” restart
    if size == offset:
        return [], offset
    records = []
    new_offset = offset
    try:
        with open(path, "rb") as handle:
            handle.seek(offset)
            chunk = handle.read()
        last_nl = chunk.rfind(b"\n")
        if last_nl < 0:
            return [], offset
        consumable = chunk[: last_nl + 1]
        new_offset = offset + len(consumable)
        consumed = 0
        lines = consumable.split(b"\n")
        for index, raw_line in enumerate(lines):
            if not raw_line.strip():
                if index == len(lines) - 1:
                    break  # split artifact after the final newline
                consumed += 1  # blank line + its newline
                new_offset = offset + consumed
                continue
            line_bytes = raw_line + b"\n"
            try:
                record = json.loads(raw_line.decode("utf-8"))
            except Exception:
                # corrupt COMPLETE line: skip over it (fail-silent,
                # progress continues) without emitting anything
                consumed += len(line_bytes)
                new_offset = offset + consumed
                continue
            if isinstance(record, dict):
                records.append(record)
            consumed += len(line_bytes)
            new_offset = offset + consumed
    except Exception:
        return [], offset
    return records, new_offset



# ---------------------------------------------------------------------------
# derivation
# ---------------------------------------------------------------------------

def _payload(record):
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else {}


def _fingerprint_of(record):
    """Patch identity may live at top level (journal) or in payload."""
    for key in ("patch_fingerprint", "fingerprint"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    payload = _payload(record)
    for key in ("patch_fingerprint", "fingerprint"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _decision_event(payload):
    allowed = bool(payload.get("allowed"))
    requires = bool(payload.get("requires_human_approval"))
    risk = str(payload.get("risk_level", "") or "")
    unknown = risk.upper() == "UNKNOWN"
    if allowed and not requires:
        event = "decision_allow"
    elif requires:
        event = "decision_review"
    elif unknown:
        event = "decision_unknown"
    else:
        event = "decision_deny"
    return event, {
        "risk_level": risk or None,
        "decision_class": event.split("_", 1)[1],
    }


# ApplyOutcomeJournal terminal truth (record_type -> emitted signals)
_JOURNAL_MAP = {
    "applied": [("apply_success", None)],
    "apply_failed": [("apply_failure", None),
                     ("run_completed", "apply_failed")],
    "verified": [("verify_success", None),
                 ("run_completed", "verified")],
    "rolled_back": [("verify_failure", None),
                    ("run_completed", "rolled_back")],
    "rollback_failed": [("apply_failure", None),
                        ("verify_failure", None),
                        ("run_completed", "rollback_failed")],
}

# Worker events (EventStore) -> signals (dedup vs journal via run_id)
_WORKER_EVENT_MAP = {
    "WorkerPatchApplied": [("apply_success", None)],
    "WorkerPatchApplyFailed": [("apply_failure", None)],
    "WorkerVerificationCompleted": [("verify_success", None)],
    "WorkerVerificationFailed": [("verify_failure", None)],
}


def _trim_runs(runs):
    if len(runs) > _RUN_KEY_CAP:
        for stale in list(runs)[: len(runs) - _RUN_KEY_CAP]:
            del runs[stale]


def _run_id_for(state, secret, keys):
    """Resolve (creating if needed) ONE run_id for a set of local keys."""
    runs = state.setdefault("runs", {})
    run_id = None
    for key in keys:
        if key:
            run_id = runs.get(key)
            if run_id is not None:
                break
    if run_id is None:
        run_id = str(uuid.uuid4())
    for key in keys:
        if key:
            runs[key] = run_id
    _trim_runs(runs)
    return run_id


def _already_emitted(state, run_id, event):
    return run_id + "|" + event in state.setdefault("emitted", set())


def _mark_emitted(state, run_id, event):
    emitted = state.setdefault("emitted", set())
    emitted.add(run_id + "|" + event)
    if len(emitted) > _EMITTED_CAP:
        for stale in list(emitted)[: len(emitted) - _EMITTED_CAP]:
            emitted.discard(stale)


def derive_usage_events(event_records, journal_records, state, ctx,
                        created_at=""):
    """Pure derivation: records + state -> (signals, new_state).

    Filesystem-free: reads nothing, writes nothing. ``ctx`` must carry
    ``secret`` (bytes) plus the signal context (version/os/install_id).
    """
    secret = ctx["secret"]
    signals = []
    run_started_keys = set(state.get("run_started_done", []))
    first_run_done = bool(state.get("first_run_done"))

    def emit(event, run_id, extra=None):
        if _already_emitted(state, run_id, event):
            return
        signals.append(build_signal(event, ctx=ctx, run_id=run_id,
                                    **(extra or {})))
        _mark_emitted(state, run_id, event)

    # --- worker events (EventStore) ---
    for record in event_records:
        event_type = str(record.get("event_type", ""))
        payload = _payload(record)
        fingerprint = _fingerprint_of(record)

        if event_type == "WorkerPatchProposed" and fingerprint:
            run_key = _run_key(secret, fingerprint)
            run_id = _run_id_for(state, secret, [run_key])
            if not first_run_done and created_at:
                emit("first_run", run_id)
                first_run_done = True
            if run_key not in run_started_keys:
                run_started_keys.add(run_key)
                emit("run_started", run_id)

        elif event_type == "WorkerRiskAssessed" and fingerprint:
            run_id = _run_id_for(
                state, secret, [_run_key(secret, fingerprint)]
            )
            name, extra = _decision_event(payload)
            emit(name, run_id, extra)

        elif event_type in _WORKER_EVENT_MAP:
            keys = []
            if fingerprint:
                keys.append(_run_key(secret, fingerprint))
            task_id = payload.get("task_id")
            if isinstance(task_id, str) and task_id:
                keys.append(_run_key(secret, task_id))
            run_id = _run_id_for(state, secret, keys)
            for name, terminal in _WORKER_EVENT_MAP[event_type]:
                extra = {"terminal_state": terminal} if terminal else None
                emit(name, run_id, extra)

    # --- apply journal (terminal truth + intent <-> fingerprint link) ---
    for record in journal_records:
        intent_id = record.get("intent_id")
        fingerprint = _fingerprint_of(record)
        keys = []
        if fingerprint:
            keys.append(_run_key(secret, fingerprint))
        if isinstance(intent_id, str) and intent_id:
            keys.append(_run_key(secret, intent_id))
        run_id = _run_id_for(state, secret, keys)
        for name, terminal in _JOURNAL_MAP.get(
            str(record.get("record_type", "")), []
        ):
            extra = {"terminal_state": terminal} if terminal else None
            emit(name, run_id, extra)

    state["run_started_done"] = list(run_started_keys)[-_RUN_KEY_CAP:]
    state["first_run_done"] = first_run_done
    return signals, state


# ---------------------------------------------------------------------------
# local persistence
# ---------------------------------------------------------------------------

def _usage_dir(usage_dir=None):
    return Path(usage_dir) if usage_dir else (tanuq_home() / "usage")


def _load_state(path):
    path = Path(path)
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                emitted = data.get("emitted", [])
                data["emitted"] = set(emitted) if isinstance(
                    emitted, list
                ) else set()
                data.setdefault("runs", {})
                data.setdefault("run_started_done", [])
                data.setdefault("first_run_done", False)
                data.setdefault("events_offset", 0)
                data.setdefault("journal_offset", 0)
                return data
    except Exception:
        pass
    return {
        "version": SCHEMA_VERSION,
        "events_offset": 0,
        "journal_offset": 0,
        "runs": {},
        "emitted": set(),
        "run_started_done": [],
        "first_run_done": False,
    }


def _save_state(path, state):
    path = Path(path)
    serializable = dict(state)
    emitted = serializable.get("emitted", set())
    if isinstance(emitted, set):
        serializable["emitted"] = sorted(emitted)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(serializable, sort_keys=True),
                   encoding="utf-8")
    tmp.replace(path)


def _append_signals(path, signals):
    if not signals:
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        for signal in signals:
            handle.write(json.dumps(signal, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


# ---------------------------------------------------------------------------
# public entry points (fail-silent)
# ---------------------------------------------------------------------------

def _context(install_id):
    return {
        "version": __version__,
        "os_family": _os_family(),
        "install_id": install_id,
    }


def collect_usage_signals(environment=None, *, workspace=None,
                          usage_dir=None, secret_path=None, persist=True):
    """Derive usage signals from local records. Fail-silent.

    Returns the list of new signals (possibly empty). Never raises,
    never writes to stdout/stderr, never affects a governance result.
    """
    try:
        env = environment
        if env is None:
            from tanuq.runtime import load_environment
            env = load_environment(workspace)
        data_dir = Path(env.data_dir)
        usage = _usage_dir(usage_dir)
        usage.mkdir(parents=True, exist_ok=True)
        state_path = usage / "state.json"
        signals_path = usage / "usage_signals.jsonl"
        state = _load_state(state_path)
        secret = load_usage_secret(secret_path)
        install_id = make_install_id(env.workspace, secret)
        ctx = _context(install_id)
        created_at = ""
        try:
            created_at = str(getattr(env.config, "created_at", "") or "")
        except Exception:
            created_at = ""
        event_records, ev_offset = read_new_records(
            data_dir / EVENTS_FILE_NAME, state.get("events_offset", 0)
        )
        journal_records, jr_offset = read_new_records(
            data_dir / APPLY_JOURNAL_FILE_NAME,
            state.get("journal_offset", 0),
        )
        signals, state = derive_usage_events(
            event_records, journal_records, state,
            dict(ctx, secret=secret), created_at
        )
        try:
            _append_signals(signals_path, signals)
            state["events_offset"] = ev_offset
            state["journal_offset"] = jr_offset
            _save_state(state_path, state)
        except Exception:
            return signals
        return signals
    except Exception:
        return []


def record_usage_error(error_class, *, environment=None, workspace=None,
                       usage_dir=None, secret_path=None, persist=True,
                       run_id=""):
    """Persist an anonymous ``error`` usage signal (FAZ 2 hook surface).

    ``error_class`` must be an error CLASS name (e.g. "ProtocolError");
    raw messages / tracebacks are rejected and never stored.
    """
    try:
        if not isinstance(error_class, str) or not error_class.strip():
            return None
        bad = (" ", "\n", "\t", "/", "\\", "(", ")", ":", ";", ".")
        if any(ch in error_class for ch in bad):
            return None
        install_id = ""
        workspace_path = None
        if environment is not None:
            workspace_path = getattr(environment, "workspace", None)
        elif workspace is not None:
            workspace_path = workspace
        if workspace_path is not None:
            secret = load_usage_secret(secret_path)
            install_id = make_install_id(workspace_path, secret)
        ctx = _context(install_id)
        signal = build_signal(
            "error", ctx=ctx, run_id=run_id or str(uuid.uuid4()),
            error_class=error_class,
        )
        if persist:
            usage = _usage_dir(usage_dir)
            usage.mkdir(parents=True, exist_ok=True)
            _append_signals(usage / "usage_signals.jsonl", [signal])
        return signal
    except Exception:
        return None
