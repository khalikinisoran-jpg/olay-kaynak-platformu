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

    def _headers(self, status, is_api=True):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
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
        got = self.headers.get("X-TANUQ-Token") or ""
        try:
            return hmac.compare_digest(got, SERVICE.token)
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
            self._headers(200, is_api=False)
            self.wfile.write(content)
            return
        if path == "/app.js":
            try:
                content = static_bytes("app.js")
            except (FileNotFoundError, ModuleNotFoundError):
                self._json(404, {"error": "UI assets missing"}, rid, t0)
                return
            self._headers(200, is_api=False)
            self.send_header("Content-Type", "application/javascript; charset=utf-8")
            self.wfile.write(content)
            return
        if path == "/api/health":
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


def _propose(data):
    from tanuq import agent_adapter
    items = data.get("proposals")
    if items is None and data.get("path"):
        items = [data]
    if not items or not isinstance(items, list):
        return {"error": "proposal JSON with path/old_content/new_content required"}
    session = data.get("session")
    try:
        response = agent_adapter.propose(SERVICE.env, json.dumps(items), session=session)
    except agent_adapter.ProtocolError as exc:
        return {"error": str(exc)}
    return response


def _pending_view():
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


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Tanuq product UI")
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--port", type=int, default=8770)
    args = ap.parse_args()
    from tanuq.runtime import load_environment
    run(load_environment(args.workspace), port=args.port)
