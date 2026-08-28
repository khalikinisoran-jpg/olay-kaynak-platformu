"""P9.6 Session Evidence & Audit Correlation — observability, not authority.

Correlation anchor: session_id. Every evidence record references session_id.
Evidence is DERIVED from authoritative sources (AgentSession state, WorkerResult,
PatchProposal fingerprints, WorkerPipelineResult) and never invents approval,
verification or rollback facts.

This module MUST NOT:
 - write files (no FileApplier)
 - execute apply (no ApplyExecutor)
 - grant approvals (no ApprovalStore.grant)
 - substitute pipeline authorization (no ApprovalStore.find_valid)
 - classify risk (no RiskEngine)
 - duplicate governance (no GovernanceEvaluator)
 - verify (no VerificationExecutor)
 - apply patches or rollback

It is observation only.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Tuple, Optional


class SessionEventType(str, Enum):
    SESSION_CREATED = "SESSION_CREATED"
    INSPECTION_COMPLETED = "INSPECTION_COMPLETED"
    PROPOSAL_READY = "PROPOSAL_READY"
    GOVERNANCE_STARTED = "GOVERNANCE_STARTED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    RESUME_REQUESTED = "RESUME_REQUESTED"
    GOVERNANCE_RESULT = "GOVERNANCE_RESULT"
    SESSION_VERIFIED = "SESSION_VERIFIED"
    SESSION_DENIED = "SESSION_DENIED"
    SESSION_FAILED = "SESSION_FAILED"
    ROLLBACK_INDICATED = "ROLLBACK_INDICATED"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class SessionEvidence:
    """Immutable auditable snapshot for one AgentSession.

    All fields are derived from authoritative session/pipeline evidence.
    Missing authoritative data is represented as "" / empty / False / "unknown"
    never as fabricated success.

    Fields:
    - session_id: deterministic anchor (authoritative: AgentSession.session_id)
    - workspace: string form of AgentSession.workspace (if available)
    - state: current SessionState value
    - proposal_set_id: advisory derived id (from fingerprints)
    - fingerprints: tuple of patch fingerprints (from WorkerResult.patches)
    - attempt: current attempt number
    - resume_count: number of explicit resume requests (from history)
    - governance_count: number of pipeline executions (from history)
    - events: tuple of correlated event dicts each containing session_id
    - failure_stage: from pipeline_result.failure_stage if available else ""
    - approval_id: only if authoritative pipeline decision provides it else ""
    - verification_passed: bool only if pipeline indicates, else False
    - rollback_indicated: True only if authoritative pipeline rollback evidence exists
    - terminal_state: VERIFIED/DENIED/FAILED or unknown
    - timestamp: snapshot generation time (ISO)
    """

    session_id: str
    workspace: str
    state: str
    proposal_set_id: str
    fingerprints: Tuple[str, ...]
    attempt: int
    resume_count: int
    governance_count: int
    events: Tuple[dict, ...]
    failure_stage: str
    approval_id: str
    verification_passed: bool
    rollback_indicated: bool
    terminal_state: str
    timestamp: str
    inspection_completed: bool
    governance_started: bool
    approval_required: bool

    @classmethod
    def from_session(cls, session) -> "SessionEvidence":
        """Build evidence deterministically from an AgentSession (read-only)."""
        # Extract authoritative fields without mutating
        sid = str(getattr(session, "session_id", ""))
        ws = str(getattr(session, "workspace", ""))
        state = str(getattr(getattr(session, "state", ""), "value", getattr(session, "state", "")))
        psid = str(getattr(session, "proposal_set_id", "") or "")
        attempt = int(getattr(session, "attempt", 1) or 1)
        resume_count = int(getattr(session, "resume_count", 0) or 0)
        governance_count = int(getattr(session, "governance_count", 0) or 0)
        history = tuple(getattr(session, "history", []) or [])

        # inspection_completed: advisory but deterministic — history contains transition to INSPECTED or inspection_result present
        insp = getattr(session, "inspection_result", None)
        inspection_completed = insp is not None or any(
            h.get("event") == "transition" and h.get("to") == "INSPECTED" for h in history
        )

        # fingerprints: from worker_result_ref if available
        fps = ()
        try:
            wr = getattr(session, "worker_result_ref", None)
            if wr is not None:
                patches = getattr(wr, "patches", ()) or ()
                fps = tuple(p.fingerprint() for p in patches)
        except Exception:
            fps = ()

        # pipeline-derived
        pipeline_result = getattr(session, "pipeline_result_ref", None)
        failure_stage = ""
        verification_passed = False
        approval_id = ""
        rollback_indicated = False
        if pipeline_result is not None:
            failure_stage = str(getattr(pipeline_result, "failure_stage", "") or "")
            verification_passed = bool(getattr(pipeline_result, "verification_passed", False))
            # approval_id only from authoritative decision
            try:
                prs = getattr(pipeline_result, "patch_results", ()) or ()
                for pr in prs:
                    dec = getattr(pr, "decision", None)
                    if dec is not None:
                        aid = str(getattr(dec, "approval_id", "") or "")
                        if aid:
                            approval_id = aid
                            break
                    # also pipeline_result approval binding via _bindings not exposed; do not invent
            except Exception:
                approval_id = ""
            # rollback indicated only if authoritative pipeline_result indicates
            try:
                for pr in getattr(pipeline_result, "patch_results", ()) or ():
                    ppr = getattr(pr, "pipeline_result", None)
                    if ppr is not None:
                        rb = getattr(ppr, "rollback", None)
                        if rb is not None:
                            rollback_indicated = True
                            break
            except Exception:
                rollback_indicated = False

        # governance_started: bool if governance_count>0
        governance_started = governance_count > 0

        # approval_required: true if failure_stage == approval or any governance indicates WAITING
        approval_required = failure_stage == "approval" or any(
            h.get("event") == "governance" and h.get("failure_stage") == "approval" for h in history
        ) or state == "WAITING_APPROVAL"

        # terminal_state: VERIFIED/DENIED/FAILED or unknown
        terminal_state = "unknown"
        if state in ("VERIFIED", "DENIED", "FAILED", "AUTHORIZED"):
            terminal_state = state
        else:
            # also from history last terminal
            if state in ("VERIFIED", "DENIED", "FAILED"):
                terminal_state = state

        # Build deterministic correlated events tuple — each event includes session_id
        events = _build_events(session, history, pipeline_result, sid)

        return cls(
            session_id=sid,
            workspace=ws,
            state=state,
            proposal_set_id=psid,
            fingerprints=fps,
            attempt=attempt,
            resume_count=resume_count,
            governance_count=governance_count,
            events=events,
            failure_stage=failure_stage,
            approval_id=approval_id,
            verification_passed=verification_passed,
            rollback_indicated=rollback_indicated,
            terminal_state=terminal_state,
            timestamp=_now_iso(),
            inspection_completed=inspection_completed,
            governance_started=governance_started,
            approval_required=approval_required,
        )


def _build_events(session, history, pipeline_result, session_id: str) -> Tuple[dict, ...]:
    """Deterministic reconstruction of session lifecycle events (observation only)."""
    evts = []

    # SESSION_CREATED always first if session exists
    evts.append({
        "type": SessionEventType.SESSION_CREATED.value,
        "session_id": session_id,
        "state": str(getattr(getattr(session, "state", ""), "value", "")) if hasattr(session, "state") else "",
        "timestamp": _now_iso(),
    })

    ws = str(getattr(session, "workspace", "") or "")

    # Map existing history entries to typed events (already session_id-anchored)
    for h in history:
        et = h.get("event", "")
        if et == "transition":
            frm = h.get("from", "")
            to = h.get("to", "")
            # Inspection completed
            if to == "INSPECTED":
                evts.append({
                    "type": SessionEventType.INSPECTION_COMPLETED.value,
                    "session_id": session_id,
                    "from": frm,
                    "to": to,
                    "workspace": ws,
                    "timestamp": _now_iso(),
                })
            # Governance started
            if to == "GOVERNING":
                evts.append({
                    "type": SessionEventType.GOVERNANCE_STARTED.value,
                    "session_id": session_id,
                    "from": frm,
                    "to": to,
                    "attempt": h.get("attempt", 1),
                    "timestamp": _now_iso(),
                })
            # Terminal
            if to == "VERIFIED":
                evts.append({
                    "type": SessionEventType.SESSION_VERIFIED.value,
                    "session_id": session_id,
                    "from": frm,
                    "to": to,
                    "timestamp": _now_iso(),
                })
            elif to == "DENIED":
                evts.append({
                    "type": SessionEventType.SESSION_DENIED.value,
                    "session_id": session_id,
                    "from": frm,
                    "to": to,
                    "reason": h.get("reason", "")[:200],
                    "timestamp": _now_iso(),
                })
            elif to == "FAILED":
                evts.append({
                    "type": SessionEventType.SESSION_FAILED.value,
                    "session_id": session_id,
                    "from": frm,
                    "to": to,
                    "reason": h.get("reason", "")[:200],
                    "timestamp": _now_iso(),
                })
            elif to == "WAITING_APPROVAL":
                evts.append({
                    "type": SessionEventType.APPROVAL_REQUIRED.value,
                    "session_id": session_id,
                    "from": frm,
                    "to": to,
                    "failure_stage": "approval",
                    "timestamp": _now_iso(),
                })
        elif et == "governance":
            evts.append({
                "type": SessionEventType.GOVERNANCE_RESULT.value,
                "session_id": session_id,
                "success": bool(h.get("success", False)),
                "failure_stage": str(h.get("failure_stage", "") or ""),
                "attempt": h.get("attempt", 1),
                "governance_count": h.get("governance_count", 0),
                "timestamp": _now_iso(),
            })
            # Distinguish verification outcome if authoritative
            if pipeline_result is not None:
                vp = bool(getattr(pipeline_result, "verification_passed", False))
                vr = bool(getattr(pipeline_result, "verification_ran", False))
                # Do not invent: only record verification_passed if pipeline says
                pass
        elif et == "resume_requested":
            evts.append({
                "type": SessionEventType.RESUME_REQUESTED.value,
                "session_id": session_id,
                "resume_count": h.get("resume_count", 1),
                "attempt": h.get("attempt", 1),
                "proposal_set_id": h.get("proposal_set_id", ""),
                "timestamp": _now_iso(),
            })

    # Proposal ready: if proposal_set_id present and fingerprints available
    psid = str(getattr(session, "proposal_set_id", "") or "")
    wr = getattr(session, "worker_result_ref", None)
    if psid and wr is not None:
        try:
            fps = tuple(p.fingerprint() for p in getattr(wr, "patches", ()))
        except Exception:
            fps = ()
        evts.append({
            "type": SessionEventType.PROPOSAL_READY.value,
            "session_id": session_id,
            "proposal_set_id": psid,
            "fingerprints": fps,
            "timestamp": _now_iso(),
        })

    # Rollback indicated: only if pipeline evidence indicates
    if pipeline_result is not None:
        try:
            for pr in getattr(pipeline_result, "patch_results", ()) or ():
                ppr = getattr(pr, "pipeline_result", None)
                if ppr is not None and getattr(ppr, "rollback", None) is not None:
                    evts.append({
                        "type": SessionEventType.ROLLBACK_INDICATED.value,
                        "session_id": session_id,
                        "path": getattr(ppr.rollback, "path", ""),
                        "success": bool(getattr(ppr.rollback, "success", False)),
                        "timestamp": _now_iso(),
                    })
                    break
        except Exception:
            pass

    # Deduplicate consecutive same-type if needed? No — keep deterministic order
    return tuple(evts)


class SessionEvidenceStore:
    """Minimal in-memory registry for correlated evidence, read-only retrieval.

    This is NOT a second governance authority; it only indexes snapshots by session_id.
    Writes are advisory record() calls; reads are side-effect free.
    """

    _store: dict = {}

    @classmethod
    def record(cls, session) -> SessionEvidence:
        """Capture current snapshot keyed by session_id (advisory)."""
        ev = SessionEvidence.from_session(session)
        cls._store[ev.session_id] = ev
        return ev

    @classmethod
    def get(cls, session_id: str) -> Optional[SessionEvidence]:
        """Read-only retrieval by session_id — no mutation, no authority."""
        if not isinstance(session_id, str) or not session_id:
            return None
        return cls._store.get(session_id)

    @classmethod
    def clear(cls):
        cls._store.clear()

    @classmethod
    def all_ids(cls):
        return tuple(cls._store.keys())


class SessionAuditReader:
    """Read-only audit interface (no side effects)."""

    @staticmethod
    def read(session) -> SessionEvidence:
        """Read evidence for a session object (or session_id via store)."""
        if isinstance(session, str):
            # session_id string lookup
            ev = SessionEvidenceStore.get(session)
            if ev is None:
                raise KeyError(f"no evidence for session_id {session!r}")
            return ev
        # session object
        return SessionEvidence.from_session(session)

    @staticmethod
    def read_by_id(session_id: str) -> Optional[SessionEvidence]:
        return SessionEvidenceStore.get(session_id)

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
            if "simulation.agent.approval.approval_ledger" in line:
                forbidden.append(line.strip())
            if "simulation.security.risk_engine" in line:
                forbidden.append(line.strip())
            if "simulation.security.governance_evaluator" in line:
                forbidden.append(line.strip())
            if "simulation.agent.verify.verification_executor" in line:
                forbidden.append(line.strip())
            if "simulation.agent.apply.apply_authorization" in line:
                forbidden.append(line.strip())
        if forbidden:
            raise AssertionError(f"SessionEvidence must not import authority modules: {forbidden}")
        code = re.sub(r'""".*?"""', '', text, flags=re.DOTALL)
        # Exclude this helper's own check lines to avoid self-trigger
        code_wo_helper = "\n".join(l for l in code.splitlines() if "_assert_no_authority" not in l)
        code_wo_helper = code_wo_helper.replace('".grant("', '').replace("'.grant('", "")
        if ".grant(" in code_wo_helper and "ApprovalStore" in code_wo_helper:
            raise AssertionError("SessionEvidence must not call ApprovalStore.grant")
        # check for approval lookup without triggering on own literal
        tmp = code_wo_helper.replace('"find' + '_valid"', '').replace("'find" + "_valid'", '')
        if "find" + "_valid" in tmp:
            raise AssertionError("SessionEvidence must not call ApprovalStore." + "find" + "_valid")
        if "File" + "Applier" in code_wo_helper:
            # allow mention in check string but not code
            filtered = "\n".join(l for l in code_wo_helper.splitlines() if "File" + "Applier" not in l or "must not" in l.lower())
            if "File" + "Applier" in filtered:
                raise AssertionError("SessionEvidence must not reference File" + "Applier")
