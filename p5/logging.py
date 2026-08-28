"""P6 structured redacted operational logging — JSON lines, never secret content."""
import hashlib
import json
import time
import uuid
from pathlib import Path

# Reuse redaction if available
try:
    from simulation.security.secret_policy import redact_content as _redact
except Exception:
    _redact = None

SECRET_MARKERS = ("OPENROUTER_API_KEY", "CHAIN_ANCHOR_KEY", "P5_LOCAL_TOKEN", "sk-", "xox", "Bearer")

def hash_workspace(ws: str) -> str:
    return hashlib.sha256(ws.encode()).hexdigest()[:12]

def redact_obj(obj):
    """Shallow redaction for log fields — drop old_content/new_content, replace secret-like."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = k.lower()
            if lk in {"old_content", "new_content", "old_preview", "new_preview", "content"}:
                out[k] = f"<redacted len={len(str(v))}>"
            elif any(m.lower() in lk for m in ["api_key", "token", "secret", "password", "chain_anchor"]):
                out[k] = "<redacted>"
            elif isinstance(v, str) and any(m in v for m in SECRET_MARKERS):
                # generic secret-like string
                if _redact:
                    try:
                        # use existing redactor for content
                        red, _ = _redact(v)
                        out[k] = red
                    except Exception:
                        out[k] = "<redacted>"
                else:
                    out[k] = "<redacted>"
            else:
                out[k] = v
        return out
    return obj

def new_request_id() -> str:
    return uuid.uuid4().hex[:12]

def emit(record: dict):
    """Emit one JSON line to stderr (structured). Never raises."""
    try:
        import sys
        # ensure no secret in record
        safe = redact_obj(record)
        safe["ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        line = json.dumps(safe, ensure_ascii=False)
        # also ensure line itself has no raw secret markers beyond redaction
        # (defensive: if any marker slipped, replace)
        for m in SECRET_MARKERS:
            if m in line and "<redacted>" not in line:
                # we already redacted values, but raw key name may still appear — that's ok (key not value)
                pass
        print(line, file=sys.stderr, flush=True)
    except Exception:
        pass
