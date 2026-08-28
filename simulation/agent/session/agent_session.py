"""P9.1 AgentSession — minimal contract and lifecycle, no authority.

Authority boundary: AgentSession is orchestration/state only.
It MUST NOT:
 - write files (no FileApplier)
 - grant approvals (no ApprovalStore.grant)
 - classify risk (no RiskEngine)
 - verify or rollback (no VerificationExecutor)
 - modify fingerprints (no PatchProposal mutation)
 - strip LLM fields (no LLMCodeAnalyzer logic duplication)

All governance/apply remains via existing WorkerActionPipeline.
"""
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Tuple


class SessionState(str, Enum):
    CREATED = "CREATED"
    INSPECTING = "INSPECTING"
    INSPECTED = "INSPECTED"  # P9.2: successful read-only inspection, not yet proposing
    PROPOSING = "PROPOSING"
    GOVERNING = "GOVERNING"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    AUTHORIZED = "AUTHORIZED"
    VERIFIED = "VERIFIED"  # P9.4: pipeline VERIFIED via existing verification
    DENIED = "DENIED"
    FAILED = "FAILED"


# Allowed transitions — explicit, deterministic, fail-closed on invalid
# P9.2 adds INSPECTED as explicit success of inspection, but keeps INSPECTING→PROPOSING for backward compat
# P9.4 adds VERIFIED as terminal after AUTHORIZED via pipeline verification
_ALLOWED = {
    SessionState.CREATED: {SessionState.INSPECTING, SessionState.FAILED},
    SessionState.INSPECTING: {SessionState.INSPECTED, SessionState.PROPOSING, SessionState.FAILED},
    SessionState.INSPECTED: {SessionState.PROPOSING, SessionState.FAILED, SessionState.DENIED},
    SessionState.PROPOSING: {SessionState.GOVERNING, SessionState.FAILED},
    SessionState.GOVERNING: {
        SessionState.WAITING_APPROVAL,
        SessionState.AUTHORIZED,
        SessionState.VERIFIED,
        SessionState.DENIED,
        SessionState.FAILED,
    },
    SessionState.WAITING_APPROVAL: {SessionState.GOVERNING, SessionState.DENIED, SessionState.FAILED},
    SessionState.AUTHORIZED: {SessionState.VERIFIED, SessionState.DENIED, SessionState.FAILED},
    SessionState.VERIFIED: set(),
    SessionState.DENIED: set(),
    SessionState.FAILED: set(),
}

# Advisory: proposal_set_id is derived, not authority
def _derive_proposal_set_id(fingerprints: Tuple[str, ...]) -> str:
    if not fingerprints:
        return ""
    joined = "|".join(sorted(fingerprints))
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=False)
class AgentSession:
    """Minimal AgentSession contract for P9.1.

    Fields are deterministic/auditable, never contain secrets.
    Attempt counting is explicit, bounded, no hidden loop.
    """

    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    goal: str = ""
    workspace: Path = field(default_factory=lambda: Path("."))
    allowed_paths: Tuple[str, ...] = field(default_factory=tuple)
    max_attempts: int = 3
    attempt: int = 1
    state: SessionState = SessionState.CREATED
    proposal_set_id: str = ""
    failure_reason: str = ""
    # Advisory references — never authority
    worker_result_ref: object = None  # WorkerResult (untrusted)
    external_action_ref: object = None  # ExternalAction (untrusted, governed via ExternalActionPipeline)
    pipeline_result_ref: object = None  # WorkerPipelineResult / ExternalPipelineResult (governance outcome)
    inspection_result: object = None  # InspectionResult (read-only evidence, advisory)
    # P9.5: audit evidence for same-session resume (advisory only, never authority)
    history: list = field(default_factory=list)
    resume_count: int = 0
    governance_count: int = 0

    def __post_init__(self):
        if not isinstance(self.session_id, str) or not self.session_id:
            raise ValueError("session_id must be non-empty string")
        if not isinstance(self.goal, str) or not self.goal.strip():
            raise ValueError("goal must be non-empty string")
        if not isinstance(self.workspace, Path):
            raise ValueError("workspace must be Path")
        # allowed_paths must be tuple of non-empty strings
        if not isinstance(self.allowed_paths, tuple):
            raise ValueError("allowed_paths must be tuple")
        for p in self.allowed_paths:
            if not isinstance(p, str) or not p:
                raise ValueError("allowed_paths entries must be non-empty strings")
        if not isinstance(self.max_attempts, int) or not (1 <= self.max_attempts <= 3):
            raise ValueError("max_attempts must be int 1..3")
        if not isinstance(self.attempt, int) or not (1 <= self.attempt <= self.max_attempts):
            raise ValueError("attempt must be 1..max_attempts")
        if not isinstance(self.state, SessionState):
            raise ValueError("state must be SessionState")
        # workspace must be absolute or will be resolved by caller; ensure no secret in state
        # Do not store old/new content

    def transition_to(self, new_state: SessionState, reason: str = "") -> None:
        """Explicit state transition, fail-closed on invalid."""
        if not isinstance(new_state, SessionState):
            raise ValueError("new_state must be SessionState")
        allowed = _ALLOWED.get(self.state, set())
        if new_state not in allowed:
            raise ValueError(f"invalid transition {self.state.value} -> {new_state.value}")
        old = self.state
        self.state = new_state
        if reason:
            # reason is advisory, never authority, and must not contain secret
            self.failure_reason = str(reason)[:500]
        # P9.5/P9.6 evidence: record transition (advisory, never authority) with correlation anchor
        try:
            self.history.append({"event": "transition", "session_id": self.session_id, "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "from": old.value, "to": new_state.value, "reason": reason[:200] if reason else "", "attempt": self.attempt})
        except Exception:
            pass

    def attach_inspection(self, inspection_result) -> None:
        """Attach read-only inspection evidence (advisory, never authority)."""
        if inspection_result is None:
            raise ValueError("inspection_result required")
        # Validate required fields minimally (advisory, not authority)
        if not hasattr(inspection_result, "requested_path"):
            raise ValueError("inspection_result must have requested_path")
        self.inspection_result = inspection_result
        # Do not auto-transition; caller must explicit transition_to

    def attach_proposal(self, worker_result) -> None:
        """Attach proposer output (untrusted) and derive advisory proposal_set_id."""
        # worker_result is untrusted (WorkerAgent output)
        if worker_result is None:
            raise ValueError("worker_result required")
        patches = getattr(worker_result, "patches", None)
        if patches is None:
            raise ValueError("worker_result must have patches")
        # Derive advisory proposal_set_id from fingerprints (sorted)
        try:
            fps = tuple(p.fingerprint() for p in patches)
        except Exception as e:
            raise ValueError(f"invalid patches: {e}")
        self.proposal_set_id = _derive_proposal_set_id(fps)
        self.worker_result_ref = worker_result
        # Clear external ref to keep single active proposal
        self.external_action_ref = None
        # Advisory: do not automatically transition; caller must explicit transition_to

    def attach_external_action(self, external_action) -> None:
        """Attach external action (untrusted) and derive advisory proposal_set_id."""
        if external_action is None:
            raise ValueError("external_action required")
        # fingerprint() is the governed identity for ExternalAction
        try:
            fp = external_action.fingerprint()
            if not isinstance(fp, str) or not fp:
                raise ValueError("fingerprint must be non-empty string")
        except Exception as e:
            raise ValueError(f"invalid external_action: {e}")
        self.proposal_set_id = _derive_proposal_set_id((fp,))
        self.external_action_ref = external_action
        # Clear worker ref to keep single active proposal
        self.worker_result_ref = None

    def record_governance(self, pipeline_result, governance_decisions=None) -> None:
        """Record governance outcome (advisory reference, not authority)."""
        self.pipeline_result_ref = pipeline_result
        self.governance_count += 1
        try:
            self.history.append({"event": "governance", "session_id": self.session_id, "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "success": bool(getattr(pipeline_result, "success", False)), "failure_stage": str(getattr(pipeline_result, "failure_stage", "")), "attempt": self.attempt, "governance_count": self.governance_count})
        except Exception:
            pass
        # Do not interpret pipeline_result as approval; just store ref

    def next_attempt(self) -> None:
        """Explicit attempt increment, bounded, no hidden loop."""
        if self.attempt >= self.max_attempts:
            raise ValueError(f"attempt {self.attempt} already at max {self.max_attempts}, no further attempts")
        self.attempt += 1
        # Reset proposal_set_id for new attempt (will be re-derived on attach)
        self.proposal_set_id = ""
        self.worker_result_ref = None
        self.external_action_ref = None
        self.pipeline_result_ref = None
        self.inspection_result = None
        # State should be reset to INSPECTING for next attempt by caller via explicit transition
        # Do not auto-transition; caller must transition_to

    def is_terminal(self) -> bool:
        return self.state in {SessionState.DENIED, SessionState.FAILED, SessionState.AUTHORIZED, SessionState.VERIFIED}

    # --- P9.5 same-session resume orchestration (never authority) ---
    def record_resume_requested(self) -> None:
        """Mark an explicit same-session resume request (advisory evidence only).

        Valid only when currently in WAITING_APPROVAL. Does NOT change attempt
        (preserves approval binding), does NOT transition state (bridge will
        transition to GOVERNING), does NOT grant approval. Purely evidence.
        """
        if self.state != SessionState.WAITING_APPROVAL:
            raise ValueError(f"resume requires WAITING_APPROVAL, was {self.state.value}")
        self.resume_count += 1
        try:
            self.history.append({"event": "resume_requested", "session_id": self.session_id, "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "resume_count": self.resume_count, "attempt": self.attempt, "proposal_set_id": self.proposal_set_id})
        except Exception:
            pass

    # --- P9.6 audit correlation (read-only, never authority) ---
    def audit_snapshot(self):
        """Read-only correlated evidence snapshot for this session (no side effects)."""
        from simulation.agent.session.session_evidence import SessionEvidence
        return SessionEvidence.from_session(self)

    # --- Authority boundary checks (for meta-test) ---
    @staticmethod
    def _assert_no_authority_imports():
        """Meta-test helper: ensure this module does not import authority primitives at top-level."""
        import pathlib
        import re
        text = pathlib.Path(__file__).read_text(encoding="utf-8")
        # Only check actual import statements outside this function's literal list
        # Find top-level imports (lines starting with import/from)
        imports = re.findall(r"^\s*(?:from|import)\s+.*$", text, flags=re.MULTILINE)
        # Filter to authority modules
        forbidden_imports = []
        for line in imports:
            if "simulation.agent.apply.file_applier" in line:
                forbidden_imports.append(line.strip())
            if "simulation.agent.approval.approval_store" in line:
                forbidden_imports.append(line.strip())
            if "simulation.security.risk_engine" in line:
                forbidden_imports.append(line.strip())
            if "simulation.agent.apply.apply_authorization" in line:
                forbidden_imports.append(line.strip())
            if "simulation.agent.apply.apply_executor" in line:
                forbidden_imports.append(line.strip())
            if "simulation.agent.verify.verification_executor" in line:
                forbidden_imports.append(line.strip())
        if forbidden_imports:
            raise AssertionError(f"AgentSession must not import authority modules: {forbidden_imports}")
