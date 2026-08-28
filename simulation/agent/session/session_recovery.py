"""P9.7-B Controlled Session Recovery — orchestration only, no authority.

Snapshot is DATA, not authority. This module reconstructs a recovery
candidate from a validated SessionSnapshot and provides an explicit
re-entry via the existing governed pipeline.

It MUST NOT:
 - call WorkerActionPipeline.execute directly as hidden auto-execution
 - call FileApplier / ApplyExecutor
 - call ApprovalStore.grant or find_valid as shortcut
 - call RiskEngine / GovernanceEvaluator as duplicate authority
 - call VerificationExecutor
 - interpret snapshot.state == VERIFIED as proof
 - restore approval_id / approved / verification_passed as authority
 - fabricate WorkerResult / PatchProposal / fingerprints

Recovery is orchestration: it re-creates an AgentSession with lifecycle
data for correlation, and explicit re-entry re-validates via
SessionGovernedBridge -> WorkerActionPipeline (sole authority).
"""
from pathlib import Path
from typing import Tuple, Optional

from simulation.agent.session.agent_session import AgentSession, SessionState


RECOVERABLE_STATES = frozenset({
    SessionState.WAITING_APPROVAL.value,
    SessionState.PROPOSING.value,
})

TERMINAL_STATES = frozenset({
    SessionState.VERIFIED.value,
    SessionState.DENIED.value,
    SessionState.FAILED.value,
    SessionState.AUTHORIZED.value,
})


class SessionRecoveryError(ValueError):
    """Fail-closed reconstruction or re-entry error."""


def _validate_snapshot(snapshot) -> None:
    if snapshot is None:
        raise SessionRecoveryError("snapshot is None")
    # snapshot already validated via load_snapshot integrity, but re-check
    if not hasattr(snapshot, "session_id") or not snapshot.session_id:
        raise SessionRecoveryError("snapshot missing session_id")
    if not hasattr(snapshot, "state") or snapshot.state not in {
        s.value for s in SessionState
    }:
        # also check VALID_SESSION_STATES string set
        raise SessionRecoveryError(f"invalid snapshot state {getattr(snapshot, 'state', None)!r}")
    if not hasattr(snapshot, "attempt") or not (1 <= snapshot.attempt <= 3):
        raise SessionRecoveryError("attempt out of bounds")
    if not hasattr(snapshot, "workspace") or not snapshot.workspace:
        raise SessionRecoveryError("missing workspace")


def reconstruct_session(
    snapshot,
    worker_result=None,
    goal: Optional[str] = None,
    allowed_paths: Optional[Tuple[str, ...]] = None,
) -> AgentSession:
    """Safe reconstruction from validated SessionSnapshot (no authority).

    Returns an AgentSession with lifecycle/history restored for correlation.
    If worker_result is supplied, its proposal_set_id must match snapshot's
    proposal_set_id (if snapshot has one), otherwise fail-closed.
    If worker_result is None and snapshot indicates proposal was present,
    the returned session will have no proposal attached and cannot re-enter
    execution until a reconnectable WorkerResult is supplied (fail-closed
    on re-entry).

    Terminal historical states are reconstructed for audit but are NOT
    automatically re-enterable (reenter will fail closed).
    """
    _validate_snapshot(snapshot)

    sid = str(snapshot.session_id)
    ws_str = str(snapshot.workspace)
    try:
        ws = Path(ws_str)
    except Exception as e:
        raise SessionRecoveryError(f"invalid workspace: {e}") from e

    # allowed_paths: explicit or derived from workspace
    if allowed_paths is None:
        allowed = (ws_str,)
    else:
        allowed = tuple(str(p) for p in allowed_paths)
        if not allowed:
            raise SessionRecoveryError("allowed_paths empty")
        # workspace confinement: workspace must be within allowed_paths (reuse PathPolicy logic minimally)
        # Simple check: workspace resolved must be within one of allowed resolved
        try:
            ws_res = ws.resolve()
            confined = False
            for ap in allowed:
                try:
                    ap_res = Path(ap).resolve()
                    if str(ws_res).startswith(str(ap_res)):
                        confined = True
                        break
                    # also handle exact match
                    if ws_res == ap_res:
                        confined = True
                        break
                except Exception:
                    continue
            if not confined:
                raise SessionRecoveryError(f"workspace {ws_str!r} outside allowed_paths {allowed!r}")
        except SessionRecoveryError:
            raise
        except Exception as e:
            raise SessionRecoveryError(f"workspace confinement check failed: {e}") from e

    state_str = str(snapshot.state)
    # Map snapshot state to SessionState enum value
    try:
        state_enum = SessionState(state_str)
    except Exception as e:
        raise SessionRecoveryError(f"invalid state {state_str!r}") from e

    g = goal if isinstance(goal, str) and goal.strip() else f"recovered:{sid}"

    # Construct session with snapshot's attempt and state directly (recovery bypasses normal transition sequence
    # because snapshot already represents validated historical lifecycle)
    try:
        session = AgentSession(
            session_id=sid,
            goal=g,
            workspace=ws,
            allowed_paths=tuple(allowed),
            max_attempts=3,
            attempt=int(snapshot.attempt),
            state=state_enum,
        )
    except Exception as e:
        raise SessionRecoveryError(f"reconstruction failed: {e}") from e

    # Restore lifecycle/correlation data (never authority)
    session.proposal_set_id = str(getattr(snapshot, "proposal_set_id", "") or "")
    session.resume_count = int(getattr(snapshot, "resume_count", 0) or 0)
    session.governance_count = int(getattr(snapshot, "governance_count", 0) or 0)
    # history deep copy
    try:
        hist = getattr(snapshot, "history", ()) or ()
        session.history = [dict(e) if isinstance(e, dict) else e for e in hist]
    except Exception:
        session.history = []

    # Do NOT restore approval_id / approved / verification_passed as authority
    # proposal identity reconnection
    if worker_result is not None:
        # worker_result is untrusted; validate not None and has patches
        patches = getattr(worker_result, "patches", None)
        if patches is None:
            raise SessionRecoveryError("worker_result missing patches")
        # Derive proposal_set_id from worker_result via AgentSession logic and compare
        import hashlib
        try:
            fps = tuple(p.fingerprint() for p in patches)
        except Exception as e:
            raise SessionRecoveryError(f"invalid worker_result patches: {e}") from e
        # Use same derivation as AgentSession
        if fps:
            joined = "|".join(sorted(fps))
            derived_psid = hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]
        else:
            derived_psid = ""
        snap_psid = str(getattr(snapshot, "proposal_set_id", "") or "")
        if snap_psid and derived_psid and snap_psid != derived_psid:
            raise SessionRecoveryError(
                f"proposal_set_id mismatch: snapshot {snap_psid!r} vs worker_result {derived_psid!r} (correlation swap)"
            )
        # Attach proposal via AgentSession (derives proposal_set_id)
        try:
            session.attach_proposal(worker_result)
        except Exception as e:
            raise SessionRecoveryError(f"attach_proposal failed: {e}") from e
        # If snapshot had no proposal_set_id but worker_result does, keep derived
        # If snapshot had one and worker_result matches, keep snapshot's (they match)
        # Ensure session.proposal_set_id now equals derived (or snapshot if empty)
        if snap_psid and session.proposal_set_id != snap_psid:
            # Should not happen if matched above, but enforce snapshot's correlation
            # Fail closed if mismatch
            raise SessionRecoveryError("proposal_set_id correlation failed after attach")
    else:
        # No worker_result supplied: if snapshot state requires proposal (WAITING, PROPOSING, GOVERNING, VERIFIED)
        # we leave session without proposal -> re-entry will fail closed (no proposal attached)
        # This is the safe "data-only" path per spec Q8
        pass

    # Ensure snapshot's proposal_set_id is preserved for correlation if worker_result not supplied
    # (already set above)

    return session


def reenter_session(
    session: AgentSession,
    pipeline,
    verify_paths=None,
    test_targets: Tuple[str, ...] = (),
) -> object:
    """Explicit governed re-entry for a recovered session (orchestration only).

    For WAITING_APPROVAL -> calls SessionGovernedBridge.resume (re-validates approval)
    For PROPOSING -> calls SessionGovernedBridge.execute
    For terminal -> fail-closed (cannot silently re-enter)
    Exactly one pipeline attempt per call, no hidden retry.
    """
    if not isinstance(session, AgentSession):
        raise SessionRecoveryError("session must be AgentSession")
    if pipeline is None:
        raise SessionRecoveryError("pipeline required")

    # Terminal cannot silently re-enter execution
    if session.state.value in TERMINAL_STATES:
        raise SessionRecoveryError(
            f"terminal historical state {session.state.value!r} cannot re-enter execution (audit only)"
        )

    # Import bridge locally to avoid circular? Bridge already imports AgentSession, safe
    from simulation.agent.session.session_governed_bridge import SessionGovernedBridge

    bridge = SessionGovernedBridge()

    if session.state == SessionState.WAITING_APPROVAL:
        if session.worker_result_ref is None:
            raise SessionRecoveryError("recovered WAITING_APPROVAL session has no reconnected proposal (missing WorkerResult)")
        # Explicit resume -> re-enters GOVERNING -> pipeline re-checks approval
        return bridge.resume(session, pipeline, verify_paths=verify_paths, test_targets=test_targets)
    elif session.state == SessionState.PROPOSING:
        if session.worker_result_ref is None:
            raise SessionRecoveryError("recovered PROPOSING session has no proposal")
        return bridge.execute(session, pipeline, verify_paths=verify_paths, test_targets=test_targets)
    elif session.state in (SessionState.CREATED, SessionState.INSPECTING, SessionState.INSPECTED, SessionState.GOVERNING):
        # For non-terminal intermediate, allow re-entry via execute if proposal present and state is PROPOSING or WAITING
        # Otherwise fail closed
        raise SessionRecoveryError(
            f"recovered state {session.state.value!r} not directly re-enterable; requires PROPOSING or WAITING_APPROVAL"
        )
    else:
        raise SessionRecoveryError(f"unsupported recovered state {session.state.value!r}")


class SessionRecovery:
    """Facade for safe reconstruction and explicit re-entry (orchestration)."""

    @staticmethod
    def reconstruct(snapshot, worker_result=None, goal=None, allowed_paths=None) -> AgentSession:
        return reconstruct_session(snapshot, worker_result=worker_result, goal=goal, allowed_paths=allowed_paths)

    @staticmethod
    def reenter(session, pipeline, verify_paths=None, test_targets=()):
        return reenter_session(session, pipeline, verify_paths=verify_paths, test_targets=test_targets)

    @staticmethod
    def is_recoverable(snapshot) -> bool:
        """Whether snapshot state is recoverable for governed re-entry (not terminal)."""
        try:
            state = getattr(snapshot, "state", "")
            return state in (SessionState.WAITING_APPROVAL.value, SessionState.PROPOSING.value)
        except Exception:
            return False

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
                # Bridge import is allowed via local import in reenter, but top-level is forbidden
                # Check if this is top-level import
                forbidden.append(line.strip())
            if "simulation.agent.apply.apply_authorization" in line:
                forbidden.append(line.strip())
        if forbidden:
            raise AssertionError(f"SessionRecovery must not import authority modules: {forbidden}")
        code = re.sub(r'""".*?"""', '', text, flags=re.DOTALL)
        code_wo = "\n".join(l for l in code.splitlines() if "_assert_no_authority" not in l)
        code_wo_check = code_wo.replace('".grant' + '("', '').replace("'.grant" + "('", "")
        if ".grant" + "(" in code_wo_check and "ApprovalStore" in code_wo_check:
            raise AssertionError("SessionRecovery must not call ApprovalStore." + "grant")
        if "find" + "_valid" in code_wo:
            raise AssertionError("SessionRecovery must not call ApprovalStore." + "find" + "_valid")
        if "File" + "Applier" in code_wo:
            raise AssertionError("SessionRecovery must not reference File" + "Applier")
        if "Apply" + "Executor" in code_wo:
            raise AssertionError("SessionRecovery must not reference Apply" + "Executor")
