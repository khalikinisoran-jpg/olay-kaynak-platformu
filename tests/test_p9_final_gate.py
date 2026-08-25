"""P9 FINAL GATE — Real end-to-end governed AgentSession.

Reuses existing chain:
Goal -> AgentSession -> RepositoryInspector -> SessionProposalAdapter
-> SessionGovernedBridge -> WorkerActionPipeline (Scope/Validation/Risk/Approval/ApplyAuthorization)
-> ApplyVerifyPipeline -> Verification/Rollback -> SessionEvidence/SessionAuditReader
"""
import json
import pathlib
import tempfile
import re
from pathlib import Path

from simulation.agent.session.agent_session import AgentSession, SessionState
from simulation.agent.session.repository_inspector import RepositoryInspector
from simulation.agent.session.session_proposal_adapter import SessionProposalAdapter
from simulation.agent.session.session_governed_bridge import SessionGovernedBridge
from simulation.agent.session.session_evidence import SessionEvidence, SessionEvidenceStore, SessionAuditReader, SessionEventType
from simulation.agent.worker.worker_result import WorkerResult
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.pipeline.apply_verify_pipeline import ApplyVerifyPipeline
from simulation.agent.pipeline.worker_action_pipeline import WorkerActionPipeline
from simulation.agent.approval.approval_ledger import ApprovalLedger
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.security.governance_evaluator import GovernanceEvaluator


def _gov_pipeline(tmp: Path, verify_real=False):
    ledger = ApprovalLedger(path=str(tmp / ".ledger.jsonl"))
    store = ApprovalStore(ledger=ledger)
    gov = GovernanceEvaluator()
    if verify_real:
        from simulation.agent.verify.verification_executor import VerificationExecutor
        vex = VerificationExecutor()
    else:
        from simulation.agent.verify.verification_result import PASS, VerificationResult
        class _Noop:
            def verify(self, paths=(), test_targets=(), **kw):
                return VerificationResult(status=PASS, exit_code=0, stdout="noop", stderr="", command=("noop",), evidence=())
            def verify_python_compile(self, paths=(), **kw):
                return self.verify(paths=paths)
        vex = _Noop()
    pipeline = WorkerActionPipeline(governance=gov, approval_store=store, scope=(str(tmp),), apply_verify_pipeline=ApplyVerifyPipeline(apply_executor=ApplyExecutor(approval_store=store), verification_executor=vex))
    return pipeline, store, gov

def _make_inspected_session(tmp: Path, sid, target="a.txt", content="hello", goal="fix"):
    (tmp / target).write_text(content, encoding="utf-8")
    insp = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path=target)
    s = AgentSession(session_id=sid, goal=goal, workspace=tmp, allowed_paths=(str(tmp),))
    s.transition_to(SessionState.INSPECTING)
    s.attach_inspection(insp)
    s.transition_to(SessionState.INSPECTED)
    return s, insp

# PART 2 — REQUIRED E2E SUCCESS PATH (HIGH -> WAITING -> external approval -> resume -> VERIFIED)
def test_p9_final_e2e_success_high_resume():
    with tempfile.TemporaryDirectory(prefix="p9final_e2e_") as td:
        tmp = Path(td)
        sid = "p9final-e2e-01"
        goal = "add api_key handling for real integration"
        s, insp = _make_inspected_session(tmp, sid, "a.txt", "hello", goal)
        assert insp.is_supported is True
        assert s.inspection_result is not None
        adapter = SessionProposalAdapter()
        # HIGH-risk via existing governance (api_key)
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test-final"', "path": str(tmp / "a.txt")}))
        assert res.success, res.failure_reason
        wr = WorkerResult(task_id="t-final", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        # Risk is system-derived
        p = res.patches[0]
        dec = gov.evaluate(p)
        assert dec.requires_human_approval is True, "must be HIGH"
        bridge = SessionGovernedBridge()
        psid_before = s.proposal_set_id
        attempt_before = s.attempt
        # First execute -> WAITING_APPROVAL
        r1 = bridge.execute(s, pipeline)
        assert s.state == SessionState.WAITING_APPROVAL, r1
        assert r1.failure_stage == "approval"
        assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello"
        assert r1.success is False
        # No approval fabricated
        ev_wait = s.audit_snapshot()
        assert ev_wait.approval_required is True
        assert ev_wait.approval_id == ""
        assert SessionEventType.APPROVAL_REQUIRED.value in [e["type"] for e in ev_wait.events]
        assert s.session_id == sid
        # External actor grants approval (session MUST NOT call grant)
        assert not hasattr(s, "grant")
        store.grant(p.fingerprint(), path=p.path, action=p.action, risk_level=dec.risk_level.value, attempt=attempt_before)
        assert len(store.consumed_ids()) == 0  # not yet consumed
        # Resume SAME session
        r2 = bridge.resume(s, pipeline)
        assert s.state == SessionState.VERIFIED, f"r2={r2}"
        assert r2.success is True
        assert r2.verification_passed is True
        assert s.session_id == sid
        assert s.proposal_set_id == psid_before
        assert s.attempt == attempt_before
        assert s.resume_count == 1
        assert s.governance_count == 2
        assert len(store.consumed_ids()) == 1  # consumed exactly once
        assert (tmp / "a.txt").read_text(encoding="utf-8") == 'hello\napi_key = "sk-test-final"'
        # Evidence correlates
        ev = s.audit_snapshot()
        assert ev.session_id == sid
        assert ev.proposal_set_id == psid_before
        assert ev.fingerprints[0] == p.fingerprint()
        assert ev.terminal_state == "VERIFIED"
        assert ev.verification_passed is True
        assert ev.approval_id != ""  # authoritative decision provides approval_id
        types = [e["type"] for e in ev.events]
        for need in [SessionEventType.SESSION_CREATED.value, SessionEventType.INSPECTION_COMPLETED.value, SessionEventType.PROPOSAL_READY.value, SessionEventType.GOVERNANCE_STARTED.value, SessionEventType.APPROVAL_REQUIRED.value, SessionEventType.RESUME_REQUESTED.value, SessionEventType.GOVERNANCE_RESULT.value, SessionEventType.SESSION_VERIFIED.value]:
            assert need in types, f"missing {need} in {types}"
        # also via SessionAuditReader
        ev2 = SessionAuditReader.read(s)
        assert ev2.session_id == sid
        assert ev2.terminal_state == "VERIFIED"
        # Verify every event anchored
        for e in ev.events:
            assert e["session_id"] == sid

# PART 3 — MULTI-FILE SUCCESS PATH preserves P8 atomicity
def test_p9_final_multi_file_preserves_p8():
    with tempfile.TemporaryDirectory(prefix="p9final_multi_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        (tmp / "b.txt").write_text("world", encoding="utf-8")
        insp_a = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        sid = "p9final-multi-01"
        s = AgentSession(session_id=sid, goal="fix both files final gate", workspace=tmp, allowed_paths=(str(tmp),))
        s.transition_to(SessionState.INSPECTING)
        s.attach_inspection(insp_a)
        s.transition_to(SessionState.INSPECTED)
        from simulation.agent.worker.patch_proposal import PatchProposal as PP
        p1 = PP(path=str(tmp / "a.txt"), action="modify", reason="fix", old_content="hello", new_content="hello fixed", allowed_paths=(str(tmp),))
        p2 = PP(path=str(tmp / "b.txt"), action="modify", reason="fix", old_content="world", new_content="world fixed", allowed_paths=(str(tmp),))
        wr = WorkerResult(task_id="t-multi", success=True, summary="t", patches=(p1, p2))
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        result = SessionGovernedBridge().execute(s, pipeline)
        assert s.state == SessionState.VERIFIED
        assert result.success is True
        assert result.apply_success is True
        assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello fixed"
        assert (tmp / "b.txt").read_text(encoding="utf-8") == "world fixed"
        ev = s.audit_snapshot()
        assert ev.session_id == sid
        assert len(ev.fingerprints) == 2
        assert p1.fingerprint() in ev.fingerprints
        assert p2.fingerprint() in ev.fingerprints
        assert ev.terminal_state == "VERIFIED"

# PART 4 — NEGATIVE / FAIL-CLOSED (stale-after-waiting)
def test_p9_final_negative_stale_fail_closed():
    with tempfile.TemporaryDirectory(prefix="p9final_neg_") as td:
        tmp = Path(td)
        sid = "p9final-neg-01"
        s, insp = _make_inspected_session(tmp, sid, "a.txt", "hello", "add api_key stale test")
        adapter = SessionProposalAdapter()
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        wr = WorkerResult(task_id="t-neg", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        bridge = SessionGovernedBridge()
        r1 = bridge.execute(s, pipeline)
        assert s.state == SessionState.WAITING_APPROVAL
        # modify target externally after WAITING
        (tmp / "a.txt").write_text("hello externally changed", encoding="utf-8")
        p = res.patches[0]
        dec = gov.evaluate(p)
        store.grant(p.fingerprint(), path=p.path, action=p.action, risk_level=dec.risk_level.value, attempt=s.attempt)
        r2 = bridge.resume(s, pipeline)
        assert s.state != SessionState.VERIFIED
        assert s.state in (SessionState.DENIED, SessionState.FAILED, SessionState.WAITING_APPROVAL)
        assert r2.failure_stage in ("validation", "apply", "approval", "verification", "rollback")
        # proof no unauthorized write
        assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello externally changed"
        ev = s.audit_snapshot()
        assert ev.session_id == sid
        assert ev.terminal_state != "VERIFIED"
        assert ev.approval_id == "" or ev.failure_stage != ""  # no fabricated approval_id if not valid
        types = [e["type"] for e in ev.events]
        assert SessionEventType.APPROVAL_REQUIRED.value in types
        # no hidden retry: exactly 2 governance attempts
        assert s.governance_count == 2
        assert s.resume_count == 1

# PART 5 — READ-ONLY EVIDENCE INTEGRITY (success + negative)
def test_p9_final_readonly_evidence_integrity():
    with tempfile.TemporaryDirectory(prefix="p9final_ro_") as td:
        tmp = Path(td)
        # success session
        sid_ok = "p9final-ro-ok"
        s_ok, insp_ok = _make_inspected_session(tmp, sid_ok, "ok.txt", "hello", "fix ok")
        (tmp / "ok.txt").write_text("hello", encoding="utf-8")
        from simulation.agent.worker.patch_proposal import PatchProposal as PP
        p_ok = PP(path=str(tmp / "ok.txt"), action="modify", reason="fix", old_content="hello", new_content="hello fixed", allowed_paths=(str(tmp),))
        s_ok.attach_proposal(WorkerResult(task_id="t", success=True, summary="t", patches=(p_ok,)))
        s_ok.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        SessionGovernedBridge().execute(s_ok, pipeline)
        assert s_ok.state == SessionState.VERIFIED
        consumed_before = len(store.consumed_ids())
        state_before = s_ok.state
        content_before = (tmp / "ok.txt").read_text(encoding="utf-8")
        ev1 = s_ok.audit_snapshot()
        ev2 = SessionAuditReader.read(s_ok)
        ev3 = SessionEvidence.from_session(s_ok)
        SessionEvidenceStore.record(s_ok)
        ev4 = SessionEvidenceStore.get(sid_ok)
        ev5 = s_ok.audit_snapshot()
        assert ev1.terminal_state == ev2.terminal_state == ev3.terminal_state == ev4.terminal_state == ev5.terminal_state == "VERIFIED"
        assert s_ok.state == state_before
        assert (tmp / "ok.txt").read_text(encoding="utf-8") == content_before
        assert len(store.consumed_ids()) == consumed_before
        assert s_ok.resume_count == 0
        assert s_ok.governance_count == 1
        # negative session
        sid_neg = "p9final-ro-neg"
        s_neg, insp_neg = _make_inspected_session(tmp, sid_neg, "neg.txt", "hello", "add api_key")
        adapter = SessionProposalAdapter()
        res = adapter.propose(s_neg, insp_neg, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "neg.txt")}))
        s_neg.attach_proposal(WorkerResult(task_id="t", success=True, summary="t", patches=res.patches))
        s_neg.transition_to(SessionState.PROPOSING)
        pipeline2, store2, gov2 = _gov_pipeline(tmp)
        r1 = SessionGovernedBridge().execute(s_neg, pipeline2)
        assert s_neg.state == SessionState.WAITING_APPROVAL
        state_neg_before = s_neg.state
        # repeated reads do not change anything
        for _ in range(3):
            _ = s_neg.audit_snapshot()
            _ = SessionAuditReader.read(s_neg)
        assert s_neg.state == state_neg_before
        assert s_neg.resume_count == 0
        assert s_neg.governance_count == 1

# PART 6 — ZERO-BYPASS META GATE
def test_p9_final_zero_bypass_meta():
    import pathlib as pl
    for rel in ["simulation/agent/session/agent_session.py", "simulation/agent/session/session_governed_bridge.py", "simulation/agent/session/session_evidence.py"]:
        src = pl.Path(rel).read_text(encoding="utf-8")
        imports = re.findall(r"^\s*(?:from|import)\s+.*$", src, flags=re.MULTILINE)
        for line in imports:
            assert "file_applier" not in line.lower(), f"FileApplier import forbidden {rel}: {line}"
            assert "apply_executor" not in line.lower(), f"ApplyExecutor import forbidden {rel}: {line}"
            assert "approval_store" not in line.lower(), f"ApprovalStore import forbidden {rel}: {line}"
            assert "risk_engine" not in line.lower(), f"RiskEngine import forbidden {rel}: {line}"
            assert "governance_evaluator" not in line.lower(), f"GovernanceEvaluator import forbidden {rel}: {line}"
            assert "verification_executor" not in line.lower(), f"VerificationExecutor import forbidden {rel}: {line}"
        # no hidden retry loop
        assert "while True" not in src or "resume" not in src.lower()
    AgentSession._assert_no_authority_imports()
    SessionGovernedBridge._assert_no_authority_imports()
    SessionAuditReader._assert_no_authority_imports()
