"""TANUQ Usage Signal remote transport (FAZ 2.2).

Fail-silent, HTTPS-only, allow-listed minimum transport between the
local Usage Signal store (FAZ 1) and a future owner-provided endpoint
(FAZ 2.3 integration). This module is a pure transport motor:

- NO real endpoint ships with TANUQ; without one this is a no-op.
- ONE HTTP request == ONE batch (POST, JSON, UTF-8).
- Explicit allow-list projection — never blanket dict forwarding.
- Single attempt, no retry, no queue, no thread, no daemon, no spool.
- Every failure (DNS, refused, timeout, TLS, 4xx/5xx, malformed URL,
  encoding, unexpected) is fail-silent: returns False, never raises
  across the public boundary, never touches stdout/stderr.
- OFF guard is re-checked here (defense in depth): when the user
  preference is OFF, no DNS / socket / requests call happens at all.
- Governance core is never imported: transport only receives already
  derived signals.

Limits (contract): signal <= 1 KB · batch <= 64 signals · batch <= 32 KB
· connect timeout 1.0 s · read timeout 2.0 s.
"""
import json
import os
import urllib.parse
from pathlib import Path

import requests

from tanuq.config import read_usage_remote_preference, user_config_path
from tanuq.usage_signal import USAGE_EVENTS

SCHEMA_VERSION = 1

# Explicit allow-list (keep in sync with usage_signal.SIGNAL_KEYS —
# parity is asserted by tests/usage_transport_test.py).
ALLOWED_SIGNAL_FIELDS = frozenset({
    "schema_version",
    "event",
    "timestamp",
    "version",
    "os_family",
    "install_id",
    "run_id",
    "risk_level",
    "decision_class",
    "terminal_state",
    "error_class",
})

SIGNAL_MAX_BYTES = 1024
BATCH_MAX_SIGNALS = 64
BATCH_MAX_BYTES = 32 * 1024
CONNECT_TIMEOUT = 1.0
READ_TIMEOUT = 2.0

_USER_AGENT = "TANUQ-UsageSignal/1"
_ENDPOINT_ENV_VAR = "TANUQ_USAGE_ENDPOINT"


# ---------------------------------------------------------------------------
# endpoint validation (HTTPS only, no credentials, no malformed URLs)
# ---------------------------------------------------------------------------

def validate_endpoint(endpoint):
    """Return the normalized https endpoint, or None (never raises)."""
    try:
        if not isinstance(endpoint, str):
            return None
        candidate = endpoint.strip()
        if not candidate or " " in candidate:
            return None
        parts = urllib.parse.urlsplit(candidate)
        if parts.scheme.lower() != "https":
            return None
        if not parts.netloc or not parts.hostname:
            return None
        if parts.username or parts.password:
            return None  # credentials in a URL are secret material
        return candidate
    except Exception:
        return None


def _endpoint_from_config():
    """Value lookup from the user config (presence helper = tanuq.config)."""
    try:
        data = json.loads(Path(user_config_path()).read_text(
            encoding="utf-8"))
        value = data.get("usage_endpoint") if isinstance(data, dict) else None
        if isinstance(value, str) and value.strip():
            return value
    except Exception:
        pass
    return None


def resolve_endpoint(endpoint=None):
    """param > TANUQ_USAGE_ENDPOINT env > user config. None = no-op.

    - an explicit ``endpoint`` argument is STRICT: valid https or None
      (never silently replaced by another source);
    - an invalid/empty env value is ignored (falls through) — the same
      deterministic rule FAZ 2.1 applies to TANUQ_USAGE;
    - a missing/invalid endpoint anywhere -> None -> no send.
    """
    if endpoint is not None:
        return validate_endpoint(endpoint)
    env_value = os.environ.get(_ENDPOINT_ENV_VAR)
    if isinstance(env_value, str) and env_value.strip():
        validated = validate_endpoint(env_value)
        if validated:
            return validated
        # invalid env -> ignored, fall through (deterministic)
    return validate_endpoint(_endpoint_from_config())


# ---------------------------------------------------------------------------
# allow-list projection + batching
# ---------------------------------------------------------------------------

def filter_signal(signal):
    """Project one signal onto the allow-list; None = drop.

    Nested/dynamic values are rejected (only str/int scalars survive).
    """
    if not isinstance(signal, dict):
        return None
    projected = {}
    for key in ALLOWED_SIGNAL_FIELDS:
        if key not in signal:
            continue
        value = signal[key]
        if isinstance(value, bool) or isinstance(value, int):
            projected[key] = value
        elif isinstance(value, str):
            projected[key] = value
        else:
            continue  # dict/list/etc: forbidden nested data -> dropped
    event = projected.get("event")
    if not isinstance(event, str) or event not in USAGE_EVENTS:
        return None
    return projected


def _encoded(signal):
    return json.dumps(signal, ensure_ascii=False, sort_keys=True,
                      allow_nan=False).encode("utf-8")


def build_batches(signals):
    """Project, size-check and chunk signals into request bodies.

    Returns a list of UTF-8 JSON byte payloads. Signals over
    SIGNAL_MAX_BYTES are dropped (never split); batches are split so
    each stays <= BATCH_MAX_SIGNALS and <= BATCH_MAX_BYTES.
    """
    accepted = []
    for signal in signals or ():
        projected = filter_signal(signal)
        if projected is None:
            continue
        if len(_encoded(projected)) > SIGNAL_MAX_BYTES:
            continue
        accepted.append(projected)

    batches = []
    current = []
    current_bytes = 0
    overhead = len(json.dumps(
        {"schema_version": SCHEMA_VERSION, "endpoint_verified": True,
         "signals": []},
        ensure_ascii=False).encode("utf-8"))
    for signal in accepted:
        size = len(_encoded(signal))
        if current and (
            len(current) >= BATCH_MAX_SIGNALS
            or current_bytes + size + overhead + len(current) + 1
            > BATCH_MAX_BYTES
        ):
            batches.append(current)
            current, current_bytes = [], 0
        current.append(signal)
        current_bytes += size
    if current:
        batches.append(current)

    payloads = []
    for batch in batches:
        body = {
            "schema_version": SCHEMA_VERSION,
            "endpoint_verified": True,
            "signals": batch,
        }
        payloads.append(json.dumps(
            body, ensure_ascii=False, sort_keys=True, allow_nan=False,
        ).encode("utf-8"))
    return payloads


# ---------------------------------------------------------------------------
# send (public boundary: fail-silent)
# ---------------------------------------------------------------------------

def send_usage_signals(signals, endpoint=None):
    """Send derived signals to the owner endpoint. Fail-silent.

    Returns True when every batch attempt completed with an HTTP
    response (any status), False when skipped or transport-failed.
    Never raises, never prints. OFF preference or a missing/invalid
    endpoint means zero network activity (no DNS, no socket, no
    requests call).
    """
    try:
        enabled, _source = read_usage_remote_preference()
        if not enabled:
            return False
        url = resolve_endpoint(endpoint)
        if not url:
            return False
        payloads = build_batches(signals)
        if not payloads:
            return False
        completed = False
        for payload in payloads:
            try:
                response = requests.post(
                    url,
                    data=payload,
                    headers={
                        "Content-Type": "application/json; charset=utf-8",
                        "User-Agent": _USER_AGENT,
                    },
                    timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                )
                del response  # any HTTP status == attempt completed
                completed = True
            except Exception:
                return False  # single attempt per batch, no retry
        return completed
    except Exception:
        return False
