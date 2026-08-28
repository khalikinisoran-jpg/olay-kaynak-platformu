"""P6 explicit validated configuration — typed, fail-closed, localhost-only.

Classification:
  SECRET: OPENROUTER_API_KEY, CHAIN_ANCHOR_KEY, P5_LOCAL_TOKEN  — never logged
  OPERATIONAL: P5_HOST, P5_PORT, P5_WORKSPACE_ROOT, P5_DATA_DIR, P5_MAX_BODY, P5_LOG_LEVEL
  PUBLIC: package version, server metadata

Precedence: CLI args > environment > defaults. Invalid values fail closed.
"""
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

ALLOWED_HOSTS = {"127.0.0.1", "localhost"}
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_MAX_BODY = 1 << 20  # 1 MiB
DEFAULT_LOG_LEVEL = "INFO"

@dataclass(frozen=True)
class P5Config:
    host: str
    port: int
    workspace_root: Path
    data_dir: Path | None  # None = per-workspace .p5_platform
    log_level: str
    max_body: int
    local_token: str | None  # secret, never logged

    @property
    def workspace_root_resolved(self) -> Path:
        return self.workspace_root.resolve()


def _parse_host(raw: str | None) -> str:
    host = (raw or DEFAULT_HOST).strip()
    if host not in ALLOWED_HOSTS:
        raise ValueError(f"P5_HOST must be one of {sorted(ALLOWED_HOSTS)} (loopback only); got {raw!r}. 0.0.0.0 is rejected.")
    return host


def _parse_port(raw: str | int | None) -> int:
    text = str(raw).strip() if raw is not None else str(DEFAULT_PORT)
    try:
        port = int(text, 10)
    except ValueError:
        raise ValueError(f"P5_PORT must be integer 1-65535; got {raw!r}")
    if not (1 <= port <= 65535):
        raise ValueError(f"P5_PORT must be 1-65535; got {port}")
    return port


def _parse_max_body(raw: str | int | None) -> int:
    text = str(raw).strip() if raw is not None else str(DEFAULT_MAX_BODY)
    try:
        val = int(text, 10)
    except ValueError:
        raise ValueError(f"P5_MAX_BODY must be positive integer; got {raw!r}")
    if val <= 0 or val > 10 * (1 << 20):
        raise ValueError(f"P5_MAX_BODY must be 1..10485760; got {val}")
    return val


def _parse_workspace_root(raw: str | None) -> Path:
    if raw is None or not str(raw).strip():
        # Default: system temp dir (safe, writable, per-OS)
        raw = tempfile.gettempdir()
    p = Path(str(raw)).expanduser()
    # must resolve safely; create if missing but do not allow traversal insanity
    try:
        resolved = p.resolve()
    except Exception as e:
        raise ValueError(f"P5_WORKSPACE_ROOT resolve failed: {e}")
    # Ensure it is absolute
    if not resolved.is_absolute():
        raise ValueError(f"P5_WORKSPACE_ROOT must be absolute; got {raw!r}")
    # Create safely inside try (only inside configured root, not arbitrary client path)
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise ValueError(f"P5_WORKSPACE_ROOT mkdir failed: {e}")
    return resolved


def load_config(cli_host=None, cli_port=None, cli_workspace_root=None, cli_data_dir=None, cli_log_level=None, cli_max_body=None, cli_token=None) -> P5Config:
    """Load validated config. CLI args override env; env overrides defaults. Fail-closed."""
    # env reads
    env_host = os.getenv("P5_HOST")
    env_port = os.getenv("P5_PORT")
    env_ws = os.getenv("P5_WORKSPACE_ROOT")
    env_data = os.getenv("P5_DATA_DIR")
    env_log = os.getenv("P5_LOG_LEVEL")
    env_max = os.getenv("P5_MAX_BODY")
    env_token = os.getenv("P5_LOCAL_TOKEN")

    host_raw = cli_host if cli_host is not None else env_host
    port_raw = cli_port if cli_port is not None else env_port
    ws_raw = cli_workspace_root if cli_workspace_root is not None else env_ws
    data_raw = cli_data_dir if cli_data_dir is not None else env_data
    log_raw = cli_log_level if cli_log_level is not None else env_log
    max_raw = cli_max_body if cli_max_body is not None else env_max
    token_raw = cli_token if cli_token is not None else env_token

    host = _parse_host(host_raw)
    port = _parse_port(port_raw)
    workspace_root = _parse_workspace_root(ws_raw)
    data_dir = Path(str(data_raw)).resolve() if data_raw else None
    log_level = (str(log_raw).strip().upper() if log_raw else DEFAULT_LOG_LEVEL)
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        raise ValueError(f"P5_LOG_LEVEL must be DEBUG/INFO/WARNING/ERROR; got {log_raw!r}")
    max_body = _parse_max_body(max_raw)
    local_token = str(token_raw).strip() if token_raw and str(token_raw).strip() else None
    # token is secret — validation only checks non-empty if provided
    if local_token is not None and len(local_token) < 8:
        raise ValueError("P5_LOCAL_TOKEN must be at least 8 chars if set")

    return P5Config(host=host, port=port, workspace_root=workspace_root, data_dir=data_dir, log_level=log_level, max_body=max_body, local_token=local_token)


def is_within_workspace_root(requested: Path, root: Path) -> bool:
    """Robust is-relative-to check compatible with Python 3.12 (and 3.9)."""
    try:
        # Python 3.9+: is_relative_to
        return requested.resolve().is_relative_to(root.resolve())
    except AttributeError:
        try:
            requested.resolve().relative_to(root.resolve())
            return True
        except Exception:
            return False
    except Exception:
        return False


def is_allowed_origin(origin: str, allowed_hosts=ALLOWED_HOSTS) -> bool:
    """P8: dynamic localhost CORS — any http://127.0.0.1:port or http://localhost:port."""
    if not origin or not isinstance(origin, str):
        return False
    try:
        from urllib.parse import urlparse
        parsed = urlparse(origin)
        if parsed.scheme != "http":
            return False
        host = parsed.hostname
        if host not in allowed_hosts:
            return False
        port = parsed.port
        # Allow any valid port 1-65535, or default 80 if not specified (but localhost without port is unlikely)
        if port is not None and not (1 <= port <= 65535):
            return False
        # No extra path/query/fragment allowed for Origin (should be just scheme://host:port)
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            # Origin header should never contain path; be strict
            if parsed.path not in ("",):
                return False
        return True
    except Exception:
        return False
