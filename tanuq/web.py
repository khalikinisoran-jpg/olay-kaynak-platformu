"""Tanuq product UI — view layer over the governed runtime.

Security contract (same discipline as the p5 demo, hardened for the
product):

- UI != AUTHORITY. The server never writes workspace files and never
  grants authority itself; every mutation goes through the existing
  governed chain via tanuq.runtime (WorkerActionPipeline, single
  GovernanceEvaluator, store-backed single-use ApprovalStore,
  ApplyAuthorization, FileApplier, VerificationExecutor, journals,
  anchored EventStore).
- Governed + anchored BY DEFAULT: the server refuses to start on an
  uninitialized workspace and always runs the anchored trust model.
- ALL state-changing POST endpoints require the local device token
  (X-TANUQ-Token, constant-time compare, fail-closed 403). GET
  endpoints are read-only views of durable evidence.
- No fake analyzer in the product flow: proposals arrive as explicit
  JSON (from the user or an agent hook).
- Data sources: EventStore, ApprovalLedger/ApprovalStore,
  ApplyOutcomeJournal, ChainAnchor and the pending store. The UI keeps
  no parallel audit state.

Honest limits (also shown in the UI): workspace/path containment only,
no OS sandbox, no network enforcement, evidence is tamper-EVIDENT
(detectable), not tamper-proof.
"""
import hmac
import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files as resource_files
from pathlib import Path
from urllib.parse import urlparse

from p5.logging import emit as log_emit, new_request_id

from simulation.security.path_policy import PathPolicy

from tanuq import __version__
from tanuq.config import APPROVAL_TTL_SECONDS, tanuq_data_dir
from tanuq.evidence import (
    blocked_from_events,
    chain_status,
    event_summary,
    journal_intents,
    read_event_records,
)
from tanuq.pending import load_pending, patch_from_record, remove_pending

MAX_BODY = 1 << 20

# First-run (setup) mode: the server can start for a workspace that is
# NOT initialized yet. In this mode only the static shell, /api/health
# and POST /api/setup are reachable — every governance endpoint stays
# 404 until setup completes (fail-closed). The UI is never an authority:
# /api/setup writes ONLY Tanuq's own init state by wrapping the exact
# CLI init sequence (resolve_workspace -> init_workspace ->
# load_environment -> ensure_local_token -> register_workspace, the
# same order as tanuq/cli.py cmd_init).
SETUP_MODE = False
SETUP_WS = None
_server_token = None


def _static_resource(name: str):
    """Locate a packaged static asset via importlib.resources.

    Resolves inside the installed package (site-packages for a wheel
    install) with no dependency on the working directory or any
    development source tree.
    """
    return resource_files("tanuq") / "static" / name


def static_bytes(name: str) -> bytes:
    return _static_resource(name).read_bytes()


class WorkspaceService:

    def __init__(self, env, token: str):
        self.env = env
        self.token = token

    @property
    def workspace(self):
        return self.env.workspace

    def anchor_key(self):
        return self.env.store.chain_anchor.key

    def chain(self):
        return chain_status(tanuq_data_dir(self.workspace), self.anchor_key())


SERVICE = None


class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def _headers(self, status, is_api=True, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        origin = self.headers.get("Origin")
        if origin and origin.startswith(("http://127.0.0.1", "http://localhost")):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-TANUQ-Token")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; "
            "style-src 'self' 'unsafe-inline'",
        )
        self.send_header("Cache-Control", "no-store" if is_api else "no-cache")
        self.end_headers()

    def _json(self, status, obj, rid=None, t0=None):
        self._headers(status)
        self.wfile.write(json.dumps(obj, ensure_ascii=False).encode("utf-8"))
        try:
            log_emit({
                "level": "INFO" if status < 400 else ("WARNING" if status < 500 else "ERROR"),
                "request_id": rid or new_request_id(),
                "method": self.command,
                "path": urlparse(self.path).path,
                "status": status,
                "duration_ms": int((time.time() - t0) * 1000) if t0 else 0,
            })
        except Exception:
            pass

    def _check_token(self) -> bool:
        expected = SERVICE.token if SERVICE is not None else _server_token
        got = self.headers.get("X-TANUQ-Token") or ""
        try:
            return hmac.compare_digest(got, expected)
        except Exception:
            return False

    def do_OPTIONS(self):
        self._headers(204, is_api=False)

    def do_GET(self):
        rid, t0 = new_request_id(), time.time()
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            try:
                content = static_bytes("index.html")
            except (FileNotFoundError, ModuleNotFoundError):
                self._json(404, {"error": "UI assets missing"}, rid, t0)
                return
            self._headers(200, is_api=False,
                          content_type="text/html; charset=utf-8")
            self.wfile.write(content)
            return
        if path == "/app.js":
            try:
                content = static_bytes("app.js")
            except (FileNotFoundError, ModuleNotFoundError):
                self._json(404, {"error": "UI assets missing"}, rid, t0)
                return
            self._headers(200, is_api=False,
                          content_type="application/javascript; charset=utf-8")
            self.wfile.write(content)
            return
        if path == "/api/health":
            if SETUP_MODE:
                self._json(200, {
                    "ok": True,
                    "service": "tanuq-ui",
                    "version": __version__,
                    "initialized": False,
                    "workspace_hint": str(SETUP_WS) if SETUP_WS else None,
                    "limits": {
                        "os_sandbox": False,
                        "network_enforcement": False,
                        "evidence": "tamper-evident (not tamper-proof)",
                    },
                }, rid, t0)
                return
            chain = SERVICE.chain()
            self._json(200, {
                "ok": True,
                "service": "tanuq-ui",
                "version": __version__,
                "governed": True,
                "anchor": chain["anchor"],
                "limits": {
                    "os_sandbox": False,
                    "network_enforcement": False,
                    "evidence": "tamper-evident (not tamper-proof)",
                },
            }, rid, t0)
            return
        if SETUP_MODE:
            self._json(404, {"error": "not found"}, rid, t0)
            return
        if path == "/api/dashboard":
            self._json(200, _dashboard(), rid, t0)
            return
        if path == "/api/pending":
            self._json(200, {"pending": _pending_view()}, rid, t0)
            return
        if path == "/api/activity":
            intents = journal_intents(SERVICE.env.apply_journal, limit=50)
            self._json(200, {"intents": intents, "source": "ApplyOutcomeJournal"}, rid, t0)
            return
        if path == "/api/blocked":
            blocked = blocked_from_events(tanuq_data_dir(SERVICE.workspace), limit=50)
            self._json(200, {"blocked": blocked, "source": "EventStore"}, rid, t0)
            return
        if path == "/api/evidence":
            chain = SERVICE.chain()
            records = read_event_records(tanuq_data_dir(SERVICE.workspace))
            self._json(200, {
                "chain_valid": chain["chain_valid"],
                "anchor": chain["anchor"],
                "events": chain["events"],
                "rows": event_summary(records, limit=200),
                "note": (
                    "Evidence is tamper-evident: any modification is "
                    "detectable. This is not an absolute immutability "
                    "guarantee."
                ),
            }, rid, t0)
            return
        if path == "/api/incidents":
            from tanuq.coordinator import OperationCoordinator
            report = OperationCoordinator(SERVICE.env).incidents()
            self._json(200, {**report, "source": "detect-only projection over journals/anchor"}, rid, t0)
            return
        if path == "/api/lineage":
            from urllib.parse import parse_qs
            qs = parse_qs(urlparse(self.path).query)
            from tanuq.evidence import lineage
            report = lineage(
                SERVICE.env,
                fingerprint=(qs.get("fingerprint") or [None])[0],
                limit=int((qs.get("limit") or ["20"])[0] or 20),
            )
            self._json(200, {**report, "source": "cross-journal projection (fingerprint-referenced, no content)"}, rid, t0)
            return
        if path == "/api/operations":
            from urllib.parse import parse_qs
            from tanuq.coordinator import OperationCoordinator
            qs = parse_qs(urlparse(self.path).query)
            report = OperationCoordinator(SERVICE.env).operations(
                fingerprint=(qs.get("fingerprint") or [None])[0],
                limit=int((qs.get("limit") or ["20"])[0] or 20),
            )
            self._json(200, {**report, "source": "projection over journals/evidence (no content)"}, rid, t0)
            return
        if path == "/api/status":
            from tanuq.coordinator import OperationCoordinator
            self._json(200, OperationCoordinator(SERVICE.env).status(), rid, t0)
            return
        self._json(404, {"error": "not found"}, rid, t0)

    def do_POST(self):
        rid, t0 = new_request_id(), time.time()
        path = urlparse(self.path).path
        if not self._check_token():
            self._json(403, {"error": "missing or invalid access token (fail-closed)"}, rid, t0)
            return
        length_raw = self.headers.get("Content-Length")
        try:
            length = int(length_raw) if length_raw is not None else 0
        except ValueError:
            self._json(400, {"error": "invalid Content-Length"}, rid, t0)
            return
        if length > MAX_BODY:
            self._json(413, {"error": "payload too large"}, rid, t0)
            return
        body = self.rfile.read(length) if length else b""
        try:
            data = json.loads(body.decode("utf-8")) if body else {}
            if not isinstance(data, dict):
                raise ValueError("JSON must be an object")
        except Exception:
            self._json(400, {"error": "malformed JSON"}, rid, t0)
            return
        try:
            if SETUP_MODE:
                if path == "/api/setup":
                    payload, status = _setup(data)
                    self._json(status, payload, rid, t0)
                    return
                self._json(404, {"error": "not found"}, rid, t0)
                return
            # /api/setup stays reachable after the in-place transition so
            # a re-run is answered 409 by the is_initialized check (same
            # contract as setup mode; it can only write Tanuq init state).
            if path == "/api/setup":
                payload, status = _setup(data)
                self._json(status, payload, rid, t0)
                return
            if path == "/api/connect":
                payload, status = _connect(data)
                self._json(status, payload, rid, t0)
                return
            if path == "/api/propose":
                self._json(200, _propose(data), rid, t0)
                return
            if path == "/api/approve":
                self._json(200, _approve(data), rid, t0)
                return
            if path == "/api/reject":
                self._json(200, _reject(data), rid, t0)
                return
            if path == "/api/execute":
                result, in_flight = _execute(data)
                # 409 CONFLICT: RAM-only in-flight slot busy (fail-closed
                # orchestration conflict, not a governance decision).
                self._json(409 if in_flight else 200, result, rid, t0)
                return
        except Exception:
            self._json(500, {"error": "internal error"}, rid, t0)
            return
        self._json(404, {"error": "not found"}, rid, t0)


def _proposal_from_payload(obj):
    return PatchProposal(
        path=obj["path"],
        action=obj.get("action", "modify"),
        reason=obj.get("reason", "ui propose"),
        old_content=obj["old_content"],
        new_content=obj["new_content"],
        allowed_paths=tuple(SERVICE.env.config.allowed_paths),
    )


def _evaluate_patch(patch):
    config = SERVICE.env.config
    in_scope, scope_message = PathPolicy().check_scope(
        patch.path, tuple(config.allowed_paths)
    )
    if not in_scope:
        return {
            "state": "DENIED",
            "risk": "UNKNOWN",
            "message": f"DENIED: outside the protected workspace ({scope_message})",
        }
    decision = SERVICE.env.governance.evaluate(patch)
    if decision.allowed is not True:
        return {
            "state": "DENIED",
            "risk": decision.risk_level.value,
            "message": "DENIED by policy (unknown proposals are always denied)",
        }
    state = (
        "APPROVAL_REQUIRED"
        if decision.requires_human_approval is True
        else "PROPOSED"
    )
    return {
        "state": state,
        "risk": decision.risk_level.value,
        "message": (
            f"Risk: {decision.risk_level.value} — "
            + (
                "approval required (single-use, fingerprint-bound, "
                f"TTL {APPROVAL_TTL_SECONDS}s)"
                if state == "APPROVAL_REQUIRED"
                else "auto-apply on execute; verification still runs"
            )
        ),
        "governance": {
            "risk": decision.risk_level.value,
            "allowed": bool(decision.allowed),
            "approval_required": bool(decision.requires_human_approval),
            "reason": decision.reason,
        },
    }


def _setup(data):
    """First-run setup endpoint (P0-1): wrap the exact CLI init sequence.

    Contract: writes ONLY Tanuq's own init state — <ws>/.tanuq/config.json,
    <ws>/.tanuq/data/, the anchor key under ~/.tanuq/keys/, the local
    device token and the workspace registry. It never touches a
    workspace source file and never invokes any governance component
    (no proposal, risk, approval, apply, verification or coordinator
    call). Errors: 400 (bad input / validation), 409 (already
    initialized), 500 (unexpected — no path or secret leakage). The
    token is never returned in a response.
    """
    from tanuq.config import (
        DEFAULT_VERIFICATION_DEPTH,
        TanuqError,
        ensure_local_token,
        init_workspace,
        is_initialized,
        register_workspace,
        resolve_workspace,
    )
    from tanuq.runtime import load_environment

    ws_raw = data.get("workspace")
    if not ws_raw or not isinstance(ws_raw, str):
        return {"error": "workspace path is required"}, 400
    allowed = data.get("allowed_paths")
    if allowed is None:
        allowed = []
    if not isinstance(allowed, list) or not all(
        isinstance(p, str) for p in allowed
    ):
        return {"error": "allowed_paths must be a list of folder paths"}, 400
    depth = data.get("verification_depth")
    if depth is None:
        depth = DEFAULT_VERIFICATION_DEPTH
    if not isinstance(depth, str):
        return {"error": "verification_depth must be a string"}, 400
    try:
        ws = resolve_workspace(ws_raw)
    except TanuqError as exc:
        return {"error": str(exc)}, 400
    if is_initialized(ws):
        return {
            "error": "This project is already protected. Reload the page.",
        }, 409
    try:
        config = init_workspace(
            ws, allowed_paths=allowed or None, verification_depth=depth)
        env = load_environment(ws)
        # cmd_init calls ensure_local_token() again after init_workspace
        # (which already calls it); it is idempotent, so the same call is
        # kept here for CLI parity with zero extra side effect.
        ensure_local_token()
        register_workspace(ws)
    except (SystemExit, TanuqError) as exc:
        return {"error": str(exc)}, 400
    except Exception:
        return {
            "error": "Setup could not be completed — details are in "
                     "the terminal that started Tanuq.",
        }, 500
    # In-place transition: the same server process now serves the full
    # governed view layer (identical to restarting 'tanuq ui'). Keep the
    # token of the CURRENT service when one is already running (e.g. a
    # second workspace initialized through an initialized-mode server).
    global SERVICE, SETUP_MODE
    SERVICE = WorkspaceService(
        env, SERVICE.token if SERVICE is not None else _server_token)
    SETUP_MODE = False
    return {
        "initialized": True,
        "workspace": str(config.workspace_path),
        "allowed_paths": list(config.allowed_paths),
        "verification_depth": config.verification_depth,
        "next": "connect-ai",
    }, 200


def _claude_hook_command():
    """The hook command written into Claude Code settings.

    Uses the interpreter THIS UI server runs under (sys.executable),
    so the tanuq package is always importable from the hook (avoids
    the observed stale-global-install friction). Absolute path,
    quoted for Windows-safe paths.
    """
    return f'"{sys.executable}" -m tanuq.claude_code_adapter'


def _connect(data):
    """Connect-AI endpoint (P0-2): install the governed Claude Code
    PreToolUse hook (Edit|Write) into <workspace>/.claude/settings.json.

    Agent-configuration only. This endpoint never enters the governance
    chain: no proposal, risk, approval, fingerprint, apply, verification,
    evidence or coordinator call. The only file it can write is the
    workspace's Claude Code settings file. Existing user settings and
    unrelated hooks are preserved (semantic merge); TANUQ hook insertion
    is idempotent (single entry, updated in place if the command
    changed); malformed existing JSON is NEVER overwritten (fail-closed
    409). Writes are atomic (tmp + replace, same pattern as
    tanuq.config.save_config). Only agent value "claude_code" is
    accepted (fail-closed 400 otherwise).
    """
    from tanuq.claude_code_adapter import _SUPPORTED_TOOLS

    if data.get("agent") != "claude_code":
        return {"error": "This release connects Claude Code only."}, 400
    settings_path = Path(SERVICE.env.workspace) / ".claude" / "settings.json"
    matcher = "|".join(_SUPPORTED_TOOLS)
    hook_entry = {
        "matcher": matcher,
        "hooks": [{"type": "command", "command": _claude_hook_command()}],
    }

    existing = None
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except Exception:
            existing = None
        if not isinstance(existing, dict):
            return {
                "error": "The existing Claude Code settings could not be "
                         "read. Fix or rename .claude/settings.json manually "
                         "— Tanuq will not overwrite your settings.",
            }, 409

    if existing is None:
        merged = {"hooks": {"PreToolUse": [hook_entry]}}
        changed = True
    else:
        merged = existing
        hooks = merged.setdefault("hooks", {})
        pre = hooks.setdefault("PreToolUse", [])
        if not isinstance(hooks, dict) or not isinstance(pre, list):
            return {
                "error": "The existing Claude Code settings have an "
                         "unexpected structure. Fix .claude/settings.json "
                         "manually — Tanuq will not overwrite your settings.",
            }, 409

        def _is_tanuq(entry):
            if not isinstance(entry, dict):
                return False
            subs = entry.get("hooks")
            return isinstance(subs, list) and any(
                isinstance(h, dict)
                and "tanuq.claude_code_adapter" in str(h.get("command", ""))
                for h in subs)

        tanuq_idx = [i for i, e in enumerate(pre) if _is_tanuq(e)]
        if not tanuq_idx:
            pre.append(hook_entry)
            changed = True
        elif pre[tanuq_idx[0]] == hook_entry and len(tanuq_idx) == 1:
            changed = False
        else:
            pre[tanuq_idx[0]] = hook_entry
            for i in sorted(tanuq_idx[1:], reverse=True):
                pre.pop(i)
            changed = True

    if changed:
        tmp = None
        try:
            settings_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = settings_path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(merged, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            tmp.replace(settings_path)
        except Exception:
            if tmp is not None:
                try:
                    tmp.unlink()
                except Exception:
                    pass
            return {
                "error": "Could not write the Claude Code settings — "
                         "check the folder permissions and try again.",
            }, 500
    return {
        "connected": True,
        "agent": "claude_code",
        "workspace": str(SERVICE.env.workspace),
        "hook": {"event": "PreToolUse", "matcher": matcher},
        "next": "open-claude-code",
    }, 200


def _propose(data):
    from tanuq.coordinator import OperationCoordinator
    items = data.get("proposals")
    if items is None and data.get("path"):
        items = [data]
    if not items or not isinstance(items, list):
        return {"error": "proposal JSON with path/old_content/new_content required"}
    session = data.get("session")
    try:
        response = OperationCoordinator(SERVICE.env).propose(
            json.dumps(items), session=session)
    except Exception as exc:
        from tanuq.agent_adapter import ProtocolError
        if isinstance(exc, ProtocolError):
            return {"error": str(exc)}
        raise
    return response


def _approval_meta_by_fp():
    """Read-only approval metadata projection per fingerprint.

    Derived solely from the hash-chained approval ledger (same
    fail-closed read pattern as the operations projection). Never an
    authority input: /api/pending only reports grant state.
    """
    try:
        records = SERVICE.env.approval_store.ledger.load()
    except Exception:
        return {}
    grants = {}
    consumed = set()
    applied = set()
    revoked = set()
    for rec in records:
        rt = rec.get("record_type", "")
        fp = rec.get("patch_fingerprint", "")
        if not fp or rt == "anchored":
            continue
        if rt == "grant":
            prev = grants.get(fp)
            if prev is None or str(rec.get("created_at", "")) > str(prev.get("created_at", "")):
                grants[fp] = rec
        elif rt == "consumed":
            consumed.add(rec.get("approval_id", ""))
        elif rt == "applied":
            applied.add(rec.get("approval_id", ""))
        elif rt == "revoked":
            revoked.add(rec.get("approval_id", ""))
    meta = {}
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for fp, g in grants.items():
        aid = g.get("approval_id", "")
        exp = g.get("expires_at", "") or ""
        if aid in applied:
            state = "applied"
        elif aid in consumed:
            state = "consumed"
        elif aid in revoked:
            state = "revoked"
        elif exp and now > exp:
            state = "expired"
        else:
            state = "granted"
        meta[fp] = {"state": state, "approval_id": aid,
                    "granted_at": g.get("created_at", ""),
                    "expires_at": exp}
    return meta


def _pending_view():
    approval_meta = _approval_meta_by_fp()
    rows = []
    for record in load_pending(SERVICE.workspace):
        try:
            patch = patch_from_record(record)
        except Exception:
            continue
        verdict = _evaluate_patch(patch)
        rows.append({
            "path": patch.path,
            "action": patch.action,
            "reason": patch.reason,
            "session": record.get("session", ""),
            "fingerprint": patch.fingerprint(),
            "fingerprint_short": patch.fingerprint()[:12],
            "approval": approval_meta.get(patch.fingerprint(), {"state": "none"}),
            "created_at": record.get("created_at", ""),
            "risk": verdict.get("risk", ""),
            "state": verdict.get("state", ""),
            "what_this_authorizes": (
                f"Approving authorizes EXACTLY this change: {patch.action} "
                f"on {patch.path} replacing the approved old content with "
                "the approved new content. The approval is bound to "
                f"fingerprint {patch.fingerprint()[:12]} and is single-use "
                f"(expires {APPROVAL_TTL_SECONDS}s after granting). Any "
                "other change requires a new approval."
            ),
            "diff": {
                "old_preview": patch.old_content[:2000],
                "new_preview": patch.new_content[:2000],
                "old_len": len(patch.old_content),
                "new_len": len(patch.new_content),
            },
        })
    return rows


def _approve(data):
    from tanuq import agent_adapter
    return agent_adapter.approve(SERVICE.env, data.get("fingerprint"))


def _reject(data):
    fingerprint = data.get("fingerprint")
    if not fingerprint:
        return {"error": "fingerprint required", "removed": 0}
    removed = remove_pending(
        SERVICE.workspace,
        [fp for fp in [r.get("fingerprint") for r in load_pending(SERVICE.workspace)]
         if fp and fp.startswith(fingerprint)],
    )
    return {"removed": removed, "fingerprint": fingerprint}


def _execute(data):
    from tanuq.coordinator import OperationCoordinator
    result = OperationCoordinator(SERVICE.env).execute(
        fingerprint=data.get("fingerprint"),
        run_all=bool(data.get("all")),
        session=data.get("session"),
    )
    return result, bool(result.get("in_flight"))


def _claude_connected():
    """Read-only check: is the Tanuq Claude Code hook installed in the
    workspace's .claude/settings.json? Never raises; any read or parse
    problem reports as not connected (fail-safe default). Returns only
    a boolean — never settings content, secrets or tokens.
    """
    settings_path = Path(SERVICE.env.workspace) / ".claude" / "settings.json"
    try:
        existing = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    if not isinstance(existing, dict):
        return False
    hooks = existing.get("hooks")
    pre = hooks.get("PreToolUse") if isinstance(hooks, dict) else None
    if not isinstance(pre, list):
        return False
    for entry in pre:
        subs = entry.get("hooks") if isinstance(entry, dict) else None
        if isinstance(subs, list) and any(
                isinstance(h, dict)
                and "tanuq.claude_code_adapter" in str(h.get("command", ""))
                for h in subs):
            return True
    return False


def _dashboard():
    env = SERVICE.env
    config = env.config
    chain = SERVICE.chain()
    intents = journal_intents(env.apply_journal)
    verified = [i for i in intents if i["terminal"] == "VERIFIED"][-3:]
    rolled = [i for i in intents if i["terminal"] in ("ROLLED_BACK", "ROLLBACK_FAILED")][-3:]
    last_terminal = intents[-1]["terminal"] if intents else None
    from tanuq.incidents import collect_incidents
    incident_report = collect_incidents(env)
    return {
        "workspace": str(env.workspace),
        "protected_scope": list(config.allowed_paths),
        "governed": True,
        "verification_depth": config.verification_depth,
        "anchor": chain["anchor"],
        "chain_valid": chain["chain_valid"],
        "events": chain["events"],
        "pending_count": len(load_pending(env.workspace)),
        "recent_verified": verified,
        "recent_rolled_back": rolled,
        "blocked_count": len(blocked_from_events(tanuq_data_dir(env.workspace))),
        "incident_count": incident_report["total"],
        "critical_incidents": incident_report["critical"],
        "last_terminal": last_terminal,
        "claude_connected": _claude_connected(),
        "limits": {
            "os_sandbox": False,
            "network_enforcement": False,
            "governed_channel_only": (
                "Tanuq governs changes proposed through Tanuq. Direct "
                "agent writes outside Tanuq are not intercepted."
            ),
            "evidence": "tamper-evident (detectable), not tamper-proof",
        },
    }


def run(env, port=8770, token=None):
    global SERVICE
    from tanuq.config import read_local_token
    token = token or read_local_token()
    if not token:
        raise SystemExit("Tanuq UI: no local access token (run 'tanuq init' or 'tanuq token')")
    SERVICE = WorkspaceService(env, token)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    chain = SERVICE.chain()
    print(f"Tanuq UI: http://127.0.0.1:{port}/  (view layer — governance is the authority)")
    print(f"  workspace: {env.workspace}")
    print(f"  governed mode: ACTIVE   anchor: {chain['anchor']}   "
          f"evidence chain: {'VALID' if chain['chain_valid'] else 'INVALID'}")
    print(f"  token: stored in ~/.tanuq/token (required for every state-changing action)")
    print("  limits: no OS sandbox, no network enforcement; evidence is "
          "tamper-evident, not tamper-proof")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def run_setup(workspace, port=8770, token=None):
    """First-run UI server: workspace is NOT initialized yet.

    Serves only the static shell, /api/health and POST /api/setup.
    The device token is still required for the setup POST (same
    fail-closed contract as every other state-changing POST); it is
    shown here once in the terminal that started Tanuq, never in a
    URL, log or API response. On successful setup the process
    transitions in place to the full governed view layer.
    """
    global SERVICE, SETUP_MODE, SETUP_WS, _server_token
    from tanuq.config import read_local_token
    token = token or read_local_token()
    if not token:
        raise SystemExit(
            "Tanuq UI: no local access token (run 'tanuq init' or 'tanuq token')")
    SETUP_MODE = True
    SETUP_WS = Path(workspace)
    _server_token = token
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Tanuq UI (first-run setup): http://127.0.0.1:{port}/")
    print(f"  workspace: {SETUP_WS}")
    print("  Device token for the browser (paste it once):")
    print(f"  {token}")
    print("  limits: no OS sandbox, no network enforcement; Tanuq governs")
    print("  changes proposed through Tanuq only; evidence is tamper-evident.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Tanuq product UI")
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--port", type=int, default=8770)
    args = ap.parse_args()
    from tanuq.config import is_initialized, resolve_workspace
    ws = resolve_workspace(args.workspace)
    if is_initialized(ws):
        from tanuq.runtime import load_environment
        run(load_environment(args.workspace), port=args.port)
    else:
        run_setup(ws, port=args.port)
