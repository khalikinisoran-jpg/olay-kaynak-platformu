"""Tanuq product CLI.

User commands:
    tanuq init      register a workspace, create config + anchor key
    tanuq propose   receive a change proposal (human flags or agent
                     JSON on stdin) and classify it through governance
    tanuq approve   grant a single-use, fingerprint-bound approval
    tanuq execute   run pending proposals through the governed pipeline
    tanuq history   read-only apply-outcome lifecycle
    tanuq verify    verify the evidence chain and anchor status
    tanuq status    workspace protection summary

Every state-changing path runs the existing governed chain
(PatchValidator -> GovernanceEvaluator -> ApprovalStore -> Controller
-> ApplyAuthorization -> FileApplier -> VerificationExecutor ->
ApplyOutcomeJournal -> EventStore/ChainAnchor). This CLI never writes
target files and never grants authority by itself.
"""
import argparse
import json
import sys
from pathlib import Path

from tanuq import __version__
from tanuq.config import (
    DEFAULT_VERIFICATION_DEPTH,
    VERIFICATION_DEPTHS,
    TanuqError,
    ensure_local_token,
    init_workspace,
    is_initialized,
    pending_path,
    register_workspace,
    resolve_workspace,
)
from tanuq.pending import load_pending, patch_from_record
from tanuq.config import TanuqNotInitialized
from tanuq.runtime import environment_or_error, load_environment


def _fail(message: str) -> int:
    print(f"Tanuq: {message}")
    return 1


def cmd_init(args) -> int:
    ws_arg = args.workspace if args.workspace else str(Path.cwd())
    try:
        ws = resolve_workspace(ws_arg)
    except TanuqError as exc:
        return _fail(str(exc))
    if is_initialized(ws) and not args.force:
        print(f"Tanuq is already initialized in {ws}")
        print("Use --force to re-register (evidence and approvals are kept).")
        return 1
    allowed = args.allowed_path if args.allowed_path else None
    depth = args.verification_depth or DEFAULT_VERIFICATION_DEPTH
    if args.yes:
        answers = {
            "allowed": allowed,
            "depth": depth,
        }
    else:
        print("Tanuq init — protect a workspace for AI coding agents.")
        print(f"Workspace: {ws}")
        raw_allowed = input(
            "Allowed paths (comma-separated, inside the workspace; "
            f"empty = whole workspace) [{ws}]: "
        ).strip()
        if raw_allowed:
            allowed = [p.strip() for p in raw_allowed.split(",") if p.strip()]
        raw_depth = input(
            f"Verification depth {list(VERIFICATION_DEPTHS)} "
            f"[{DEFAULT_VERIFICATION_DEPTH}]: "
        ).strip()
        if raw_depth:
            depth = raw_depth
        answers = {"allowed": allowed, "depth": depth}
    try:
        config = init_workspace(
            ws,
            allowed_paths=answers["allowed"],
            verification_depth=answers["depth"],
        )
    except TanuqError as exc:
        return _fail(str(exc))
    load_environment(ws)
    ensure_local_token()
    register_workspace(ws)
    print()
    print(f"Tanuq initialized: {ws}")
    print(f"Protected scope: {list(config.allowed_paths)}")
    print(f"Verification depth: {config.verification_depth}")
    print("Governed mode: ON (HIGH/CRITICAL require your approval; UNKNOWN is denied)")
    print("Anchored evidence: ON (tamper-evident event chain + approval ledger)")
    print()
    print("Security boundaries (honest limits):")
    print("- Tanuq governs changes proposed through the tanuq CLI/hook.")
    print("- No OS sandbox: an agent writing outside Tanuq is not intercepted.")
    print("- No network control. External network providers are not implemented.")
    print()
    print("Next: point your AI agent at 'tanuq propose' (JSON on stdin) or")
    print("run 'tanuq status' to see the protection summary.")
    return 0


def cmd_propose(args) -> int:
    from tanuq.coordinator import OperationCoordinator
    env = _load_env_or_error_quiet(args.workspace)
    ws = env.workspace
    if args.stdin_json:
        payload_text = sys.stdin.buffer.read().decode("utf-8")
    else:
        if not args.file or args.old_content is None or args.new_content is None:
            return _fail(
                "propose needs --file/--old-content/--new-content, or "
                "--stdin-json with a JSON proposal for agent hooks."
            )
        raw = Path(args.file)
        target = raw if raw.is_absolute() else (ws / raw)
        payload_text = json.dumps([{
            "path": str(target.resolve()),
            "action": "modify",
            "reason": args.reason or "tanuq propose",
            "old_content": args.old_content,
            "new_content": args.new_content,
        }])
    try:
        response = OperationCoordinator(env).propose(
            payload_text, session=args.session)
    except Exception as exc:
        from tanuq.agent_adapter import ProtocolError
        if isinstance(exc, ProtocolError):
            return _fail(str(exc))
        raise
    results = response["proposals"]
    if args.json:
        print(json.dumps(response, ensure_ascii=False, indent=2))
    else:
        print(f"Tanuq propose — workspace {ws}")
        if args.session:
            print(f"Session: {args.session}")
        for r in results:
            if r.get("state") == "ERROR":
                print(f"- (invalid payload): {r['message']}")
                continue
            print(f"- {r['path']}")
            print(f"  State: {r['state']}  Fingerprint: {r['fingerprint_short']}")
            gov = r.get("governance") or {}
            if gov.get("reason"):
                print(f"  Reason: {gov['reason']}")
            print(f"  {r['message']}")
            if r.get("warning"):
                print(f"  Warning: {r['warning']}")
        print(f"Pending proposals: {response['pending_count']}")
        if any(r.get("state") == "DENIED" for r in results):
            print("Denied proposals are NOT saved. Blocked actions are visible in 'tanuq history' evidence.")
    return 0 if not response["denied"] else 1


def cmd_approve(args) -> int:
    from tanuq import agent_adapter
    env = _load_env_or_error_quiet(args.workspace)
    pending = load_pending(env.workspace)
    if not pending:
        print(f"No pending proposals in {pending_path(env.workspace)}")
        print("Run 'tanuq propose' first.")
        return 1
    if args.fingerprint and not any(
        r.get("fingerprint", "").startswith(args.fingerprint)
        for r in pending
    ):
        return _fail(f"No pending proposal matches fingerprint {args.fingerprint!r}")
    response = agent_adapter.approve(env, args.fingerprint)
    for grant in response["granted"]:
        print(
            f"APPROVED {grant['path']} fingerprint={grant['fingerprint_short']} "
            f"approval_id={grant['approval_id'][:8]} "
            f"risk={grant['risk']} single-use TTL={grant['ttl_seconds']}s"
        )
    print(f"Granted {response['count']} approval(s).")
    print("Approvals are bound to the exact proposal fingerprint and are single-use.")
    return 0 if response["count"] > 0 else 1


def cmd_execute(args) -> int:
    env = _load_env_or_error_quiet(args.workspace)
    ws = env.workspace
    pending = load_pending(ws)
    if not pending:
        print("No pending proposals. Run 'tanuq propose' first.")
        return 1
    if args.fingerprint and not any(
        r.get("fingerprint", "").startswith(args.fingerprint)
        for r in pending
    ):
        return _fail(f"No pending proposal matches fingerprint {args.fingerprint!r}")
    if not args.fingerprint and not args.all and len(pending) > 1:
        print(
            f"{len(pending)} pending proposal(s); executing the oldest "
            "one. Use --all for the whole queue or --fingerprint for a "
            "specific proposal."
        )
    from tanuq.coordinator import OperationCoordinator
    response = OperationCoordinator(env).execute(
        fingerprint=args.fingerprint,
        run_all=args.all,
        session=args.session,
    )
    if response.get("error"):
        if response.get("in_flight"):
            print(f"Tanuq: {response['error']}.")
            print(
                "Fail-closed: wait for the running execution to finish, "
                "then retry."
            )
            return 1
        return _fail(response["error"])
    state, stage = response["terminal"], response["failure_stage"]
    print("=" * 60)
    print(f"Tanuq execute — terminal state: {state}")
    print("=" * 60)
    if response.get("related_sessions"):
        print(f"Session(s): {', '.join(response['related_sessions'])}")
    print(f"Apply success: {response['apply_success']}")
    print(f"Verification passed: {response['verification_passed']}")
    if stage:
        print(f"Failure stage: {stage}")
    if response.get("reason"):
        print(f"Reason: {response['reason']}")
    for patch in response["patches"]:
        print(f"- {patch['path']} fingerprint={patch['fingerprint_short']}")
    if state == "VERIFIED":
        print("Change applied and verified. Evidence recorded in the tamper-evident journal.")
        print("Run 'tanuq history' to see the lifecycle, 'tanuq verify' to check the chain.")
        return 0
    if state == "DENIED":
        if stage in ("validation", "risk"):
            print("The proposal was permanently denied (out of scope or policy) and removed from the queue.")
            print("The agent must submit a corrected proposal via 'tanuq propose'.")
        elif stage == "approval":
            print("Approval missing or already used (single-use). Run 'tanuq approve' and re-execute.")
        else:
            print("Blocked by policy. The proposal stays pending.")
        return 1
    if state == "ROLLED_BACK":
        print("Verification FAILED — the change was automatically rolled back.")
        print("Evidence: ROLLED_BACK recorded in the journal (apply success was never verification success).")
        return 1
    print("The operation did not reach a verified state. See 'tanuq history'.")
    return 1


def _load_env_quiet(workspace=None):
    """Load the runtime without the recovery banner polluting stdout
    (keeps machine-readable JSON output parseable)."""
    import contextlib
    import io
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            return load_environment(workspace)
    except TanuqError as exc:
        raise SystemExit(f"Tanuq: {exc}")


def _load_env_or_error_quiet(workspace=None):
    try:
        return _load_env_quiet(workspace)
    except TanuqError as exc:
        raise SystemExit(f"Tanuq: {exc}")


def cmd_history(args) -> int:
    from tanuq.coordinator import OperationCoordinator
    try:
        env = _load_env_quiet(args.workspace)
    except SystemExit as exc:
        return _fail(str(exc).replace("Tanuq: ", ""))
    except TanuqError as exc:
        return _fail(str(exc))
    selector = args.operation or args.fingerprint
    report = OperationCoordinator(env).operations(
        fingerprint=args.fingerprint,
        operation_id=args.operation,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    ops = report["operations"]
    print(f"Tanuq history — {report['count']} operation(s) "
          "(projection over journals/evidence; no content)")
    if not ops:
        print("No operations recorded yet.")
        return 0
    for op in ops:
        session = f"  session={','.join(op['sessions'])}" if op["sessions"] else ""
        print(f"{op['state']:<17} op={op['operation_id'][:12]}  "
              f"{op['path']}{session}")
        risk = op.get("risk")
        if risk:
            print(f"    risk={risk['risk']}  reason={risk['reason']!r}")
        denied_reason = op.get("denied_reason")
        if op["state"] == "DENIED" and denied_reason:
            print(f"    denied: {denied_reason!r}")
        if op["incidents"]:
            print(f"    incidents={', '.join(op['incidents'])}")
    return 0


def cmd_pending(args) -> int:
    from tanuq.pending import load_pending as _load
    try:
        env = _load_env_quiet(args.workspace)
    except SystemExit as exc:
        return _fail(str(exc).replace("Tanuq: ", ""))
    except TanuqError as exc:
        return _fail(str(exc))
    records = _load(env.workspace)
    rows = []
    for record in records:
        try:
            patch = patch_from_record(record)
        except Exception:
            continue
        decision = env.governance.evaluate(patch)
        signals = [
            f"{n}={v}"
            for n, v in (getattr(decision.assessment, "signals", ()) or ())
        ]
        rows.append({
            "fingerprint": patch.fingerprint(),
            "fingerprint_short": patch.fingerprint()[:12],
            "path": patch.path,
            "action": patch.action,
            "reason": patch.reason,
            "risk": decision.risk_level.value,
            "approval_required": bool(decision.requires_human_approval),
            "reason": decision.reason,
            "signals": signals,
            "session": record.get("session", ""),
            "created_at": record.get("created_at", ""),
        })
    if args.json:
        print(json.dumps({"pending": rows, "count": len(rows)},
                         ensure_ascii=False, indent=2))
        return 0
    print(f"Tanuq pending — {len(rows)} proposal(s)")
    for row in rows:
        print("-" * 60)
        print(f"{row['path']}  [{row['risk']}]"
              + ("  APPROVAL REQUIRED" if row["approval_required"] else ""))
        print(f"  fingerprint: {row['fingerprint_short']}  "
              f"action: {row['action']}  session: {row['session'] or '-'}")
        print(f"  reason:      {row['reason']!r}")
        print(f"  governance:  {row['reason']}")
        if row["signals"]:
            print(f"  signals:     {', '.join(row['signals'])}")
        print(f"  created:     {row['created_at'] or '-'}")
    if not rows:
        print("No pending proposals.")
    return 0


def _chain_status(ws):
    from tanuq.config import read_anchor_key
    from tanuq.evidence import chain_status
    data_dir = tanuq_data_dir_ws(ws)
    try:
        key = read_anchor_key(ws)
    except TanuqError:
        key = None
    return chain_status(data_dir, key)


def tanuq_data_dir_ws(ws: Path):
    return ws / ".tanuq" / "data"


def cmd_verify(args) -> int:
    env = _load_env_or_error_quiet(args.workspace)
    status = _chain_status(env.workspace)
    anchor = status["anchor"]
    print("Tanuq evidence verification")
    print(f"  Events in chain: {status['events']}")
    print(f"  Evidence chain:  {'VALID' if status['chain_valid'] else 'INVALID'}")
    if anchor == "ACTIVE":
        print("  Anchor:          ACTIVE (keyed chain-head verified)")
    elif anchor == "MISSING":
        print("  Anchor:          MISSING")
    else:
        print(f"  Anchor:          {anchor} (chain head does not match the keyed anchor)")
    ledger_ok = True
    try:
        env.approval_store.ledger.load()
    except Exception:
        ledger_ok = False
    print(f"  Approval ledger: {'VALID' if ledger_ok else 'INVALID (fail-closed)'}")
    if status["chain_valid"] and ledger_ok and anchor == "ACTIVE":
        print("OVERALL: evidence is tamper-evident and intact.")
        return 0
    print("OVERALL: EVIDENCE PROBLEM — do not trust the history; investigate before continuing.")
    return 1


def cmd_status(args) -> int:
    try:
        env = _load_env_quiet(args.workspace)
    except SystemExit as exc:
        return _fail(str(exc).replace("Tanuq: ", ""))
    except TanuqError as exc:
        return _fail(str(exc))
    ws = env.workspace
    config = env.config
    status = _chain_status(ws)
    pending = load_pending(ws)
    if getattr(args, "json", False):
        from tanuq.coordinator import OperationCoordinator as _OC
        ops_json = _OC(env).operations(limit=5)["operations"]
        incidents_json = _OC(env).incidents()
        print(json.dumps({
            "workspace": str(ws),
            "protected_scope": list(config.allowed_paths),
            "governed_mode": True,
            "verification_depth": config.verification_depth,
            "evidence": {
                "chain_valid": status["chain_valid"],
                "anchor": status["anchor"],
                "events": status["events"],
            },
            "pending": [
                {"path": r.get("path"), "fingerprint": r.get("fingerprint", ""),
                 "action": r.get("action"), "session": r.get("session")}
                for r in pending
            ],
            "recent_operations": [
                {"state": op["state"], "path": op["path"],
                 "sessions": op["sessions"]}
                for op in ops_json
            ],
            "incidents": {"total": incidents_json["total"],
                          "critical": incidents_json["critical"]},
        }, ensure_ascii=False, indent=2))
        return 0
    print("Tanuq status")
    print(f"  Workspace:          {ws}")
    print(f"  Protected scope:    {list(config.allowed_paths)}")
    print(f"  Governed mode:      ON")
    print(f"  Verification depth: {config.verification_depth}")
    print(f"  Evidence chain:     {'VALID' if status['chain_valid'] else 'INVALID'} "
          f"(anchor {status['anchor']}, {status['events']} events)")
    print(f"  Pending proposals:  {len(pending)}")
    if pending:
        for record in pending:
            session = f" [session: {record['session']}]" if record.get("session") else ""
            print(f"    - {record.get('path')} fingerprint={record.get('fingerprint', '')[:12]}{session}")
    from tanuq.coordinator import OperationCoordinator
    ops = OperationCoordinator(env).operations(limit=5)["operations"]
    print("  Recent operations:")
    if ops:
        for op in ops:
            session = f" [{','.join(op['sessions'])}]" if op["sessions"] else ""
            print(f"    {op['state']:<17} {op['path']}{session}")
    else:
        print("    (none yet)")
    report = OperationCoordinator(env).incidents()
    print(f"  Active incidents:   {report['total']}"
          f" ({report['critical']} critical)" if report["total"] else
          "  Active incidents:   0")
    for incident in report["incidents"]:
        print(f"    - [{incident['severity']}] {incident['type']}: {incident['current_state']}")
    if report["total"]:
        print("    Run 'tanuq incidents' for details and recommended actions.")
    return 0


def cmd_incidents(args) -> int:
    from tanuq.coordinator import OperationCoordinator
    try:
        env = _load_env_quiet(args.workspace)
    except SystemExit as exc:
        return _fail(str(exc).replace("Tanuq: ", ""))
    except TanuqError as exc:
        return _fail(str(exc))
    report = OperationCoordinator(env).incidents()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if not report["critical"] else 1
    print(f"Tanuq incidents — {report['total']} active "
          f"({report['critical']} critical), detected {report['detected_at']}")
    if not report["incidents"]:
        print("No incidents. Workspace state is clean.")
        return 0
    for incident in report["incidents"]:
        print("-" * 60)
        print(f"[{incident['severity'].upper()}] {incident['type']}")
        if incident["operation"]:
            print(f"  Operation:  {incident['operation']}")
        if incident["path"]:
            print(f"  Path:       {incident['path']}")
        print(f"  State:      {incident['current_state']}")
        print(f"  Recovery:   {incident['recovery_status']}")
        print(f"  Action:     {incident['recommended_action']}")
        if incident["detail"]:
            print(f"  Detail:     {incident['detail']}")
    print("-" * 60)
    print("Incidents are detect-only; repair always requires an explicit,")
    print("separately-authorized operator decision (fail-closed).")
    return 0 if not report["critical"] else 1


def cmd_lineage(args) -> int:
    from tanuq.coordinator import OperationCoordinator
    try:
        env = _load_env_quiet(args.workspace)
    except SystemExit as exc:
        return _fail(str(exc).replace("Tanuq: ", ""))
    except TanuqError as exc:
        return _fail(str(exc))
    report = OperationCoordinator(env).lineage(
        env, fingerprint=args.fingerprint, limit=args.limit)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    print(f"Tanuq lineage — {report['count']} operation chain(s) "
          "(fingerprint-referenced evidence, no content)")
    if not report["chains"]:
        print("No operations recorded yet.")
        return 0
    for chain in report["chains"]:
        print("=" * 60)
        print(f"Fingerprint: {chain['fingerprint_short']}  Path: {chain['path']}")
        if chain["sessions"]:
            print(f"  Session(s):   {', '.join(chain['sessions'])}")
        proposal = chain.get("proposal")
        if proposal:
            print(f"  Proposal:     {proposal['action']} via {proposal['task_id'] or '(unnamed)'}"
                  f"  reason={proposal['reason']!r}")
        risk = chain.get("risk")
        if risk:
            signals = ", ".join(f"{n}={v}" for n, v in risk.get("signals", []))
            print(f"  Risk:         {risk['risk']} allowed={risk['allowed']} "
                  f"approval_required={risk['approval_required']}")
            print(f"                reason={risk['reason']!r}"
                  + (f"  signals=[{signals}]" if signals else ""))
        for approval in chain["approvals"]:
            print(f"  Approval:     {approval.get('approval_id', '')[:8]} "
                  f"status={approval.get('status', 'granted')} "
                  f"authorizer={approval.get('authorizer', '')} "
                  f"risk={approval.get('risk', '')}")
        execution = chain.get("execution")
        if execution:
            print(f"  Execution:    {execution['intent_id'][:8]} "
                  f"{' -> '.join(execution['lifecycle'])}")
        if chain.get("denied_reason"):
            print(f"  Denial:       {chain['denied_reason']}")
        print(f"  Outcome:      {chain['outcome'] or 'PENDING'}")
        refs = chain["refs"]
        if refs:
            print(f"  Evidence seq: {min(refs)}..{max(refs)} ({len(refs)} events)")
    print("=" * 60)
    return 0


def cmd_workspace(args) -> int:
    from tanuq.config import list_registered_workspaces
    entries = list_registered_workspaces()
    if args.prune:
        kept = [e for e in entries if Path(e.get("path", "")).exists()]
        removed = len(entries) - len(kept)
        from tanuq.config import tanuq_home, WORKSPACES_FILE_NAME
        target = tanuq_home() / WORKSPACES_FILE_NAME
        tmp = target.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(kept, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(target)
        print(f"Pruned {removed} missing workspace entr(y/ies); {len(kept)} kept.")
        entries = kept
    print(f"Tanuq workspaces — {len(entries)} registered")
    for entry in entries:
        path = entry.get("path", "")
        exists = "ok" if Path(path).exists() else "MISSING"
        print(f"  - {path}  [{exists}]  registered {entry.get('registered_at', '')}")
    if not entries:
        print("Run 'tanuq init' in a workspace to register it.")
    return 0


def cmd_export(args) -> int:
    from tanuq.coordinator import OperationCoordinator
    try:
        env = _load_env_quiet(args.workspace)
    except SystemExit as exc:
        return _fail(str(exc).replace("Tanuq: ", ""))
    except TanuqError as exc:
        return _fail(str(exc))
    bundle = OperationCoordinator(env).export()
    payload = json.dumps(bundle, ensure_ascii=False, indent=2)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(payload, encoding="utf-8")
        print(f"Evidence bundle written: {out_path}")
        print(f"  operations: {bundle['lineage']['count']}  "
              f"incidents: {bundle['incidents']['total']}  "
              f"chain: {'VALID' if bundle['evidence']['chain_valid'] else 'INVALID'} "
              f"(anchor {bundle['evidence']['anchor']})")
        print("  Read-only projection; fingerprint/hash references only, no content.")
        return 0 if bundle["evidence"]["chain_valid"] else 1
    print(payload)
    return 0 if bundle["evidence"]["chain_valid"] else 1


def cmd_token(args) -> int:
    from tanuq.config import ensure_local_token
    token = ensure_local_token()
    print(token)
    return 0


def cmd_ui(args) -> int:
    from tanuq.config import ensure_local_token, read_local_token
    from tanuq import web
    try:
        env = _load_env_quiet(args.workspace)
    except TanuqError as exc:
        return _fail(str(exc))
    token = ensure_local_token()
    web.run(env, port=args.port, token=token)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tanuq",
        description=(
            "Tanuq — local agent governance runtime. "
            "AI works. You stay in control."
        ),
    )
    parser.add_argument("--version", action="version", version=f"Tanuq {__version__}")
    sub = parser.add_subparsers(dest="command")

    p_init = sub.add_parser("init", help="Register a workspace and activate protection")
    p_init.add_argument("--workspace", default=None, help="Workspace path (default: current directory)")
    p_init.add_argument("--allowed-path", action="append", default=None, help="Allowed path inside the workspace (repeatable)")
    p_init.add_argument("--verification-depth", default=None, choices=list(VERIFICATION_DEPTHS))
    p_init.add_argument("--yes", action="store_true", help="Non-interactive init with defaults")
    p_init.add_argument("--force", action="store_true", help="Re-register an already initialized workspace")
    p_init.set_defaults(func=cmd_init)

    p_propose = sub.add_parser("propose", help="Submit a change proposal through governance")
    p_propose.add_argument("--workspace", default=None)
    p_propose.add_argument("--file", default=None, help="Target file (human mode)")
    p_propose.add_argument("--old-content", default=None)
    p_propose.add_argument("--new-content", default=None)
    p_propose.add_argument("--reason", default="tanuq propose")
    p_propose.add_argument("--session", default=None, help="Optional session label for observability")
    p_propose.add_argument("--stdin-json", action="store_true", help="Read proposal JSON (object or array) from stdin — agent hook mode")
    p_propose.add_argument("--json", action="store_true", help="Machine-readable output (for agent hooks)")
    p_propose.set_defaults(func=cmd_propose)

    p_approve = sub.add_parser("approve", help="Grant a single-use approval for pending HIGH/CRITICAL proposals")
    p_approve.add_argument("--workspace", default=None)
    p_approve.add_argument("--fingerprint", default=None, help="Approve only the proposal matching this fingerprint (full or prefix)")
    p_approve.set_defaults(func=cmd_approve)

    p_execute = sub.add_parser("execute", help="Execute pending proposals through the governed pipeline")
    p_execute.add_argument("--workspace", default=None)
    p_execute.add_argument("--fingerprint", default=None, help="Execute only the proposal matching this fingerprint (full or prefix)")
    p_execute.add_argument("--all", action="store_true", help="Execute the whole pending queue (fail-fast, coordinated rollback)")
    p_execute.add_argument("--session", default=None, help="Optional session label for observability")
    p_execute.set_defaults(func=cmd_execute)

    p_history = sub.add_parser("history", help="Operation history (projection over evidence)")
    p_history.add_argument("--workspace", default=None)
    p_history.add_argument("--operation", default=None, help="Only operations matching this operation/intent id (prefix)")
    p_history.add_argument("--fingerprint", default=None, help="Only operations matching this fingerprint (prefix)")
    p_history.add_argument("--limit", type=int, default=20)
    p_history.add_argument("--json", action="store_true", help="Machine-readable output")
    p_history.set_defaults(func=cmd_history)

    p_pending = sub.add_parser("pending", help="Show pending proposals with governance detail")
    p_pending.add_argument("--workspace", default=None)
    p_pending.add_argument("--json", action="store_true", help="Machine-readable output")
    p_pending.set_defaults(func=cmd_pending)

    p_verify = sub.add_parser("verify", help="Verify the evidence chain and anchor")
    p_verify.add_argument("--workspace", default=None)
    p_verify.set_defaults(func=cmd_verify)

    p_status = sub.add_parser("status", help="Protection summary for the workspace")
    p_status.add_argument("--workspace", default=None)
    p_status.add_argument("--json", action="store_true", help="Machine-readable output")
    p_status.set_defaults(func=cmd_status)

    p_incidents = sub.add_parser("incidents", help="List active incidents (detect-only)")
    p_incidents.add_argument("--workspace", default=None)
    p_incidents.add_argument("--json", action="store_true", help="Machine-readable output")
    p_incidents.set_defaults(func=cmd_incidents)

    p_lineage = sub.add_parser("lineage", help="Cross-journal operation lineage per fingerprint")
    p_lineage.add_argument("--workspace", default=None)
    p_lineage.add_argument("--fingerprint", default=None, help="Only chains matching this fingerprint (full or prefix)")
    p_lineage.add_argument("--limit", type=int, default=20)
    p_lineage.add_argument("--json", action="store_true", help="Machine-readable output")
    p_lineage.set_defaults(func=cmd_lineage)

    p_export = sub.add_parser("export", help="Read-only secret-safe evidence bundle (JSON)")
    p_export.add_argument("--workspace", default=None)
    p_export.add_argument("--out", default=None, help="Write the JSON bundle to this file instead of stdout")
    p_export.set_defaults(func=cmd_export)

    p_token = sub.add_parser("token", help="Show (or create) the local UI access token")
    p_token.set_defaults(func=cmd_token)

    p_workspace = sub.add_parser("workspace", help="List registered workspaces on this device")
    p_workspace.add_argument("--prune", action="store_true", help="Remove entries whose path no longer exists")
    p_workspace.set_defaults(func=cmd_workspace)

    p_ui = sub.add_parser("ui", help="Start the Tanuq product UI for this workspace")
    p_ui.add_argument("--workspace", default=None)
    p_ui.add_argument("--port", type=int, default=8770)
    p_ui.set_defaults(func=cmd_ui)

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except RuntimeError as exc:
        return _fail(f"fail-closed: {exc}")


if __name__ == "__main__":
    sys.exit(main())
