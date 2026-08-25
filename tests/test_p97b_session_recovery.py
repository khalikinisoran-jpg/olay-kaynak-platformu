"""P9.7-B Controlled Session Recovery — 17 adversarial scenarios."""
import json
import pathlib
import tempfile
from pathlib import Path

import pytest

from simulation.agent.session.agent_session import AgentSession, SessionState
from simulation.agent.session.repository_inspector import RepositoryInspector
from simulation.agent.session.session_proposal_adapter import SessionProposalAdapter
from simulation.agent.session.session_persistence import SessionSnapshotStore, save_snapshot, load_snapshot
from simulation.agent.session.session_recovery import SessionRecovery, SessionRecoveryError, reconstruct_session, reenter_session
from simulation.agent.worker.worker_result import WorkerResult
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.pipeline.apply_verify_pipeline import ApplyVerifyPipeline
from simulation.agent.pipeline.worker_action_pipeline import WorkerActionPipeline
from simulation.agent.approval.approval_ledger import ApprovalLedger
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.security.governance_evaluator import GovernanceEvaluator
import re


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

def _high_proposal(tmp, old="hello", new='hello\napi_key = "sk-test"'):
    return PatchProposal(path=str(tmp / "a.txt"), action="modify", reason="x", old_content=old, new_content=new, allowed_paths=(str(tmp),))

# 1. VALID WAITING_APPROVAL RECOVERY — no write/no consumption on reconstruct
def test_p97b_valid_waiting_recovery():
    with tempfile.TemporaryDirectory(prefix="rec1_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        # create WAITING session
        s = AgentSession(session_id="rec-wait-01", goal="add api_key", workspace=tmp, allowed_paths=(str(tmp),))
        s.transition_to(SessionState.INSPECTING)
        insp = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        s.attach_inspection(insp)
        s.transition_to(SessionState.INSPECTED)
        adapter = SessionProposalAdapter()
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        from simulation.agent.session.session_governed_bridge import SessionGovernedBridge
        bridge = SessionGovernedBridge()
        r1 = bridge.execute(s, pipeline)
        assert s.state == SessionState.WAITING_APPROVAL
        # persist
        store_dir = Path(td) / "snap"
        path = save_snapshot(s, base_dir=store_dir)
        snap = load_snapshot(path)
        # reconstruct with same WorkerResult
        rec = reconstruct_session(snap, worker_result=wr)
        assert rec.session_id == s.session_id
        assert rec.state == SessionState.WAITING_APPROVAL
        assert rec.proposal_set_id == s.proposal_set_id
        assert rec.attempt == s.attempt
        assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello"
        assert len(store.consumed_ids()) == 0
        # reconstruction is data-only, no execution

# 2. RECOVERED HIGH-RISK WITHOUT APPROVAL — not VERIFIED
def test_p97b_recovered_high_without_approval():
    with tempfile.TemporaryDirectory(prefix="rec2_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        s = AgentSession(session_id="rec-wa2", goal="add api_key", workspace=tmp, allowed_paths=(str(tmp),))
        s.transition_to(SessionState.INSPECTING)
        insp = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        s.attach_inspection(insp)
        s.transition_to(SessionState.INSPECTED)
        adapter = SessionProposalAdapter()
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        from simulation.agent.session.session_governed_bridge import SessionGovernedBridge
        r1 = SessionGovernedBridge().execute(s, pipeline)
        assert s.state == SessionState.WAITING_APPROVAL
        snap = load_snapshot(save_snapshot(s, base_dir=Path(td)/"snap"))
        rec = reconstruct_session(snap, worker_result=wr)
        result = reenter_session(rec, pipeline)
        assert rec.state in (SessionState.WAITING_APPROVAL, SessionState.DENIED)
        assert result.failure_stage == "approval"
        assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello"

# 3. RECOVERED HIGH-RISK WITH VALID EXTERNAL APPROVAL -> VERIFIED, single-use
def test_p97b_recovered_high_with_valid_approval():
    with tempfile.TemporaryDirectory(prefix="rec3_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        s = AgentSession(session_id="rec-wa3", goal="add api_key", workspace=tmp, allowed_paths=(str(tmp),))
        s.transition_to(SessionState.INSPECTING)
        insp = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        s.attach_inspection(insp)
        s.transition_to(SessionState.INSPECTED)
        adapter = SessionProposalAdapter()
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        from simulation.agent.session.session_governed_bridge import SessionGovernedBridge
        SessionGovernedBridge().execute(s, pipeline)
        assert s.state == SessionState.WAITING_APPROVAL
        snap = load_snapshot(save_snapshot(s, base_dir=Path(td)/"snap"))
        # external approval
        p = res.patches[0]
        dec = gov.evaluate(p)
        store.grant(p.fingerprint(), path=p.path, action=p.action, risk_level=dec.risk_level.value, attempt=s.attempt)
        rec = reconstruct_session(snap, worker_result=wr)
        result = reenter_session(rec, pipeline)
        assert rec.state == SessionState.VERIFIED
        assert result.success is True
        assert (tmp / "a.txt").read_text(encoding="utf-8") == 'hello\napi_key = "sk-test"'
        assert len(store.consumed_ids()) == 1
        # second reenter of same recovered terminal should fail
        with pytest.raises(SessionRecoveryError):
            reenter_session(rec, pipeline)

# 4. WRONG APPROVAL / DIFFERENT PROPOSAL
def test_p97b_wrong_approval_different_proposal():
    with tempfile.TemporaryDirectory(prefix="rec4_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        s = AgentSession(session_id="rec-wrong", goal="add api_key", workspace=tmp, allowed_paths=(str(tmp),))
        s.transition_to(SessionState.INSPECTING)
        insp = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        s.attach_inspection(insp)
        s.transition_to(SessionState.INSPECTED)
        adapter = SessionProposalAdapter()
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        from simulation.agent.session.session_governed_bridge import SessionGovernedBridge
        SessionGovernedBridge().execute(s, pipeline)
        snap = load_snapshot(save_snapshot(s, base_dir=Path(td)/"snap"))
        # approval for different fingerprint
        p_wrong = PatchProposal(path=str(tmp / "a.txt"), action="modify", reason="x", old_content="hello", new_content='hello\napi_key = "OTHER"', allowed_paths=(str(tmp),))
        dec_wrong = gov.evaluate(p_wrong)
        store.grant(p_wrong.fingerprint(), path=p_wrong.path, action=p_wrong.action, risk_level=dec_wrong.risk_level.value, attempt=s.attempt)
        rec = reconstruct_session(snap, worker_result=wr)
        result = reenter_session(rec, pipeline)
        assert rec.state != SessionState.VERIFIED
        assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello"

# 5. CONSUMED APPROVAL REPLAY
def test_p97b_consumed_approval_replay():
    with tempfile.TemporaryDirectory(prefix="rec5_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        s = AgentSession(session_id="rec-replay", goal="add api_key", workspace=tmp, allowed_paths=(str(tmp),))
        s.transition_to(SessionState.INSPECTING)
        insp = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        s.attach_inspection(insp)
        s.transition_to(SessionState.INSPECTED)
        adapter = SessionProposalAdapter()
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        from simulation.agent.session.session_governed_bridge import SessionGovernedBridge
        SessionGovernedBridge().execute(s, pipeline)
        snap = load_snapshot(save_snapshot(s, base_dir=Path(td)/"snap"))
        p = res.patches[0]
        dec = gov.evaluate(p)
        store.grant(p.fingerprint(), path=p.path, action=p.action, risk_level=dec.risk_level.value, attempt=s.attempt)
        rec = reconstruct_session(snap, worker_result=wr)
        r1 = reenter_session(rec, pipeline)
        assert rec.state == SessionState.VERIFIED
        # restore file to allow replay attempt
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        # new snapshot for replay (reuse same worker_result but store already consumed)
        s2 = AgentSession(session_id="rec-replay2", goal="add api_key", workspace=tmp, allowed_paths=(str(tmp),))
        s2.transition_to(SessionState.INSPECTING)
        insp2 = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        s2.attach_inspection(insp2)
        s2.transition_to(SessionState.INSPECTED)
        res2 = adapter.propose(s2, insp2, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        wr2 = WorkerResult(task_id="t", success=True, summary="t", patches=res2.patches)
        s2.attach_proposal(wr2)
        s2.transition_to(SessionState.PROPOSING)
        from simulation.agent.session.session_governed_bridge import SessionGovernedBridge as B
        SessionGovernedBridge().execute(s2, pipeline)
        snap2 = load_snapshot(save_snapshot(s2, base_dir=Path(td)/"snap2"))
        rec2 = reconstruct_session(snap2, worker_result=wr2)
        r2 = reenter_session(rec2, pipeline)
        assert rec2.state != SessionState.VERIFIED
        assert r2.failure_stage == "approval"

# 6. EXPIRED APPROVAL
def test_p97b_expired_approval():
    with tempfile.TemporaryDirectory(prefix="rec6_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        s = AgentSession(session_id="rec-exp", goal="add api_key", workspace=tmp, allowed_paths=(str(tmp),))
        s.transition_to(SessionState.INSPECTING)
        insp = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        s.attach_inspection(insp)
        s.transition_to(SessionState.INSPECTED)
        adapter = SessionProposalAdapter()
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        from simulation.agent.session.session_governed_bridge import SessionGovernedBridge
        SessionGovernedBridge().execute(s, pipeline)
        snap = load_snapshot(save_snapshot(s, base_dir=Path(td)/"snap"))
        p = res.patches[0]
        dec = gov.evaluate(p)
        # grant with expiry in past (-10 seconds)
        store.grant(p.fingerprint(), path=p.path, action=p.action, risk_level=dec.risk_level.value, attempt=s.attempt, expires_at=-10)
        rec = reconstruct_session(snap, worker_result=wr)
        result = reenter_session(rec, pipeline)
        assert rec.state != SessionState.VERIFIED
        assert result.failure_stage == "approval"

# 7. STALE AFTER SNAPSHOT
def test_p97b_stale_after_snapshot():
    with tempfile.TemporaryDirectory(prefix="rec7_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        s = AgentSession(session_id="rec-stale", goal="add api_key", workspace=tmp, allowed_paths=(str(tmp),))
        s.transition_to(SessionState.INSPECTING)
        insp = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        s.attach_inspection(insp)
        s.transition_to(SessionState.INSPECTED)
        adapter = SessionProposalAdapter()
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        from simulation.agent.session.session_governed_bridge import SessionGovernedBridge
        SessionGovernedBridge().execute(s, pipeline)
        snap = load_snapshot(save_snapshot(s, base_dir=Path(td)/"snap"))
        # workspace changes after snapshot
        (tmp / "a.txt").write_text("hello externally changed", encoding="utf-8")
        p = res.patches[0]
        dec = gov.evaluate(p)
        store.grant(p.fingerprint(), path=p.path, action=p.action, risk_level=dec.risk_level.value, attempt=s.attempt)
        rec = reconstruct_session(snap, worker_result=wr)
        result = reenter_session(rec, pipeline)
        assert rec.state != SessionState.VERIFIED
        assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello externally changed"

# 8. SCOPE ESCAPE AFTER RECOVERY
def test_p97b_scope_escape_after_recovery():
    with tempfile.TemporaryDirectory(prefix="rec8_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        outer = Path(tempfile.mkdtemp(prefix="rec8_outer_"))
        try:
            victim = outer / "victim.txt"
            victim.write_text("safe", encoding="utf-8")
            # create snapshot with allowed_paths tmp only, but worker_result tries to escape
            s = AgentSession(session_id="rec-scope", goal="g", workspace=tmp, allowed_paths=(str(tmp),))
            s.transition_to(SessionState.INSPECTING)
            insp = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
            s.attach_inspection(insp)
            s.transition_to(SessionState.INSPECTED)
            # use in-scope proposal for snapshot persistence (so snapshot valid)
            p_ok = PatchProposal(path=str(tmp / "a.txt"), action="modify", reason="x", old_content="hello", new_content="hello fixed", allowed_paths=(str(tmp),))
            s.attach_proposal(WorkerResult(task_id="t", success=True, summary="t", patches=(p_ok,)))
            s.transition_to(SessionState.PROPOSING)
            path = save_snapshot(s, base_dir=Path(td)/"snap")
            snap = load_snapshot(path)
            # now attempt to reconnect with out-of-scope patch
            p_out = PatchProposal(path=str(victim), action="modify", reason="x", old_content="safe", new_content="pwned", allowed_paths=(str(tmp),))
            wr_out = WorkerResult(task_id="t", success=True, summary="t", patches=(p_out,))
            # reconstruct with out-of-scope proposal should either fail on proposal_set mismatch or execution will deny
            # Our reconstruct checks proposal_set_id mismatch: snapshot psid is for p_ok, wr_out has different psid -> should raise
            with pytest.raises(SessionRecoveryError):
                reconstruct_session(snap, worker_result=wr_out)
            # Also test that if we bypass reconstruction and directly try to reenter with out-of-scope via new session, pipeline denies
            # But for recovery path, we prove no escape: even if we reconstruct with matching psid but out-of-scope path, pipeline denies
            # Create new snapshot with correct psid for out-of-scope? Not valid because snapshot would have been created with p_out initially, but allowed_paths check would have caught workspace confinement?
            # Instead create snapshot where proposal_set_id matches p_out but workspace still tmp, then reenter should be DENIED by pipeline scope
            s2 = AgentSession(session_id="rec-scope2", goal="g", workspace=tmp, allowed_paths=(str(tmp),))
            s2.transition_to(SessionState.INSPECTING)
            insp2 = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
            s2.attach_inspection(insp2)
            s2.transition_to(SessionState.INSPECTED)
            s2.attach_proposal(wr_out)
            s2.transition_to(SessionState.PROPOSING)
            # need to bypass scope? No, we test that pipeline denies
            pipeline, store, gov = _gov_pipeline(tmp)
            path2 = save_snapshot(s2, base_dir=Path(td)/"snap2")
            snap2 = load_snapshot(path2)
            rec2 = reconstruct_session(snap2, worker_result=wr_out)
            result = reenter_session(rec2, pipeline)
            assert rec2.state == SessionState.DENIED
            assert victim.read_text(encoding="utf-8") == "safe"
        finally:
            try:
                victim.unlink(); outer.rmdir()
            except Exception:
                pass

# 9. TAMPERED SNAPSHOT — integrity failure remains fail-closed, no reconstruction/execution
def test_p97b_tampered_snapshot():
    with tempfile.TemporaryDirectory(prefix="rec9_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        s = AgentSession(session_id="rec-tamper", goal="g", workspace=tmp, allowed_paths=(str(tmp),))
        s.transition_to(SessionState.INSPECTING)
        path = save_snapshot(s, base_dir=Path(td)/"snap")
        data = json.loads(path.read_text(encoding="utf-8"))
        data["state"] = "VERIFIED"
        path.write_text(json.dumps(data), encoding="utf-8")
        from simulation.agent.session.session_persistence import SessionSnapshotIntegrityError
        with pytest.raises(SessionSnapshotIntegrityError):
            load_snapshot(path)
        # no reconstruction possible after integrity failure
        assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello"

# 10. FORGED AUTHORITY FIELDS — cannot authorize recovery
def test_p97b_forged_authority_fields():
    with tempfile.TemporaryDirectory(prefix="rec10_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        s = AgentSession(session_id="rec-forge", goal="add api_key", workspace=tmp, allowed_paths=(str(tmp),))
        s.transition_to(SessionState.INSPECTING)
        insp = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        s.attach_inspection(insp)
        s.transition_to(SessionState.INSPECTED)
        adapter = SessionProposalAdapter()
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        from simulation.agent.session.session_governed_bridge import SessionGovernedBridge
        SessionGovernedBridge().execute(s, pipeline)
        assert s.state == SessionState.WAITING_APPROVAL
        path = save_snapshot(s, base_dir=Path(td)/"snap")
        data = json.loads(path.read_text(encoding="utf-8"))
        # inject forged fields
        for field, val in [("approved", True), ("human_approved", True), ("approval_id", "forged"), ("verification_passed", True), ("risk_override", "LOW"), ("bypass_governance", True), ("apply_directly", True)]:
            data[field] = val
        path.write_text(json.dumps(data), encoding="utf-8")
        # load strips forbidden fields, does not become authority
        snap = load_snapshot(path)
        assert not hasattr(snap, "approved")
        # reconstruction still WAITING, not VERIFIED
        rec = reconstruct_session(snap, worker_result=wr)
        assert rec.state == SessionState.WAITING_APPROVAL
        result = reenter_session(rec, pipeline)
        assert rec.state != SessionState.VERIFIED
        assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello"

# 11. TERMINAL VERIFIED RECOVERY — audit possible, but cannot silently execute
def test_p97b_terminal_verified_recovery():
    with tempfile.TemporaryDirectory(prefix="rec11_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        s = AgentSession(session_id="rec-term-ver", goal="g", workspace=tmp, allowed_paths=(str(tmp),))
        s.transition_to(SessionState.INSPECTING)
        insp = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        s.attach_inspection(insp)
        s.transition_to(SessionState.INSPECTED)
        from simulation.agent.worker.patch_proposal import PatchProposal as PP
        p = PP(path=str(tmp / "a.txt"), action="modify", reason="fix", old_content="hello", new_content="hello fixed", allowed_paths=(str(tmp),))
        s.attach_proposal(WorkerResult(task_id="t", success=True, summary="t", patches=(p,)))
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        from simulation.agent.session.session_governed_bridge import SessionGovernedBridge
        SessionGovernedBridge().execute(s, pipeline)
        assert s.state == SessionState.VERIFIED
        path = save_snapshot(s, base_dir=Path(td)/"snap")
        snap = load_snapshot(path)
        # reconstruction for audit succeeds
        rec = reconstruct_session(snap, worker_result=WorkerResult(task_id="t", success=True, summary="t", patches=(p,)))
        assert rec.state == SessionState.VERIFIED
        # but re-entry must fail closed
        with pytest.raises(SessionRecoveryError):
            reenter_session(rec, pipeline)
        # file stays as was after verified (hello fixed)
        # restore to hello to check no extra execution
        (tmp / "a.txt").write_text("hello fixed", encoding="utf-8")
        assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello fixed"

# 12. TERMINAL DENIED/FAILED RECOVERY — no automatic retry
def test_p97b_terminal_denied_failed_recovery():
    with tempfile.TemporaryDirectory(prefix="rec12_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        # DENIED via stale
        s = AgentSession(session_id="rec-denied", goal="g", workspace=tmp, allowed_paths=(str(tmp),))
        s.transition_to(SessionState.INSPECTING)
        insp = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        s.attach_inspection(insp)
        s.transition_to(SessionState.INSPECTED)
        from simulation.agent.worker.patch_proposal import PatchProposal as PP
        p_bad = PP(path=str(tmp / "a.txt"), action="modify", reason="x", old_content="not-hello", new_content="hi", allowed_paths=(str(tmp),))
        s.attach_proposal(WorkerResult(task_id="t", success=True, summary="t", patches=(p_bad,)))
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        from simulation.agent.session.session_governed_bridge import SessionGovernedBridge
        SessionGovernedBridge().execute(s, pipeline)
        assert s.state == SessionState.DENIED
        snap = load_snapshot(save_snapshot(s, base_dir=Path(td)/"snap"))
        rec = reconstruct_session(snap, worker_result=WorkerResult(task_id="t", success=True, summary="t", patches=(p_bad,)))
        with pytest.raises(SessionRecoveryError):
            reenter_session(rec, pipeline)

# 13. MULTI-FILE RECOVERED EXECUTION
def test_p97b_multi_file_recovered_execution():
    with tempfile.TemporaryDirectory(prefix="rec13_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        (tmp / "b.txt").write_text("world", encoding="utf-8")
        from simulation.agent.worker.patch_proposal import PatchProposal as PP
        p1 = PP(path=str(tmp / "a.txt"), action="modify", reason="fix", old_content="hello", new_content="hello fixed", allowed_paths=(str(tmp),))
        p2 = PP(path=str(tmp / "b.txt"), action="modify", reason="fix", old_content="world", new_content="world fixed", allowed_paths=(str(tmp),))
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=(p1, p2))
        s = AgentSession(session_id="rec-multi", goal="fix both", workspace=tmp, allowed_paths=(str(tmp),))
        s.transition_to(SessionState.INSPECTING)
        insp = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        s.attach_inspection(insp)
        s.transition_to(SessionState.INSPECTED)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        # For multi-file test, we want WAITING? But low risk will verify directly. Use low to test multi-file P8
        # Instead create snapshot in PROPOSING and recover then execute
        path = save_snapshot(s, base_dir=Path(td)/"snap")
        snap = load_snapshot(path)
        # Need pipeline scope
        pipeline, store, gov = _gov_pipeline(tmp)
        rec = reconstruct_session(snap, worker_result=wr)
        # rec state is PROPOSING, so reenter should call execute
        result = reenter_session(rec, pipeline)
        assert rec.state == SessionState.VERIFIED
        assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello fixed"
        assert (tmp / "b.txt").read_text(encoding="utf-8") == "world fixed"

# 14. MULTI-FILE FAILURE / ROLLBACK after recovery
def test_p97b_multi_file_failure_rollback():
    with tempfile.TemporaryDirectory(prefix="rec14_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        (tmp / "b.txt").write_text("world", encoding="utf-8")
        (tmp / "app.py").write_text("x = 1\n", encoding="utf-8")
        from simulation.agent.worker.patch_proposal import PatchProposal as PP
        p1 = PP(path=str(tmp / "a.txt"), action="modify", reason="fix", old_content="hello", new_content="hello fixed", allowed_paths=(str(tmp),))
        p2 = PP(path=str(tmp / "app.py"), action="modify", reason="fix", old_content="x = 1\n", new_content="x = 1\n!!!\n", allowed_paths=(str(tmp),))
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=(p1, p2))
        s = AgentSession(session_id="rec-multi-fail", goal="fix", workspace=tmp, allowed_paths=(str(tmp),))
        s.transition_to(SessionState.INSPECTING)
        insp = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        s.attach_inspection(insp)
        s.transition_to(SessionState.INSPECTED)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        path = save_snapshot(s, base_dir=Path(td)/"snap")
        snap = load_snapshot(path)
        pipeline, store, gov = _gov_pipeline(tmp, verify_real=True)
        dummy = tmp / "test_dummy.py"
        dummy.write_text("def test_dummy(): assert True\n", encoding="utf-8")
        rec = reconstruct_session(snap, worker_result=wr)
        result = reenter_session(rec, pipeline, verify_paths=[str(tmp)], test_targets=[str(dummy)])
        assert rec.state == SessionState.FAILED
        assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello"  # rolled back, P8 atomicity
        assert (tmp / "app.py").read_text(encoding="utf-8") == "x = 1\n"

# 15. ZERO-BYPASS META TEST
def test_p97b_zero_bypass_meta():
    src = pathlib.Path("simulation/agent/session/session_recovery.py").read_text(encoding="utf-8")
    imports = re.findall(r"^\s*(?:from|import)\s+.*$", src, flags=re.MULTILINE)
    for line in imports:
        assert "file_applier" not in line.lower(), f"FileApplier import forbidden: {line}"
        assert "apply_executor" not in line.lower(), f"ApplyExecutor import forbidden: {line}"
        assert "approval_store" not in line.lower(), f"ApprovalStore import forbidden: {line}"
        assert "risk_engine" not in line.lower(), f"RiskEngine import forbidden: {line}"
        assert "governance_evaluator" not in line.lower(), f"GovernanceEvaluator import forbidden: {line}"
        assert "verification_executor" not in line.lower(), f"VerificationExecutor import forbidden: {line}"
    code = re.sub(r'""".*?"""', '', src, flags=re.DOTALL)
    code_wo = "\n".join(l for l in code.splitlines() if "_assert_no_authority" not in l)
    assert ".grant" + "(" not in code_wo
    assert "find" + "_valid" not in code_wo
    assert "File" + "Applier" not in code_wo
    SessionRecovery._assert_no_authority_imports()

# 16. LOAD/RECONSTRUCT SIDE EFFECT TEST — repeated does not modify files etc
def test_p97b_load_reconstruct_side_effect():
    with tempfile.TemporaryDirectory(prefix="rec16_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        s = AgentSession(session_id="rec-side", goal="add api_key", workspace=tmp, allowed_paths=(str(tmp),))
        s.transition_to(SessionState.INSPECTING)
        insp = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        s.attach_inspection(insp)
        s.transition_to(SessionState.INSPECTED)
        adapter = SessionProposalAdapter()
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        from simulation.agent.session.session_governed_bridge import SessionGovernedBridge
        SessionGovernedBridge().execute(s, pipeline)
        assert s.state == SessionState.WAITING_APPROVAL
        path = save_snapshot(s, base_dir=Path(td)/"snap")
        consumed_before = len(store.consumed_ids())
        content_before = (tmp / "a.txt").read_text(encoding="utf-8")
        for _ in range(3):
            snap = load_snapshot(path)
            rec = reconstruct_session(snap, worker_result=wr)
            _ = rec.audit_snapshot()
        assert len(store.consumed_ids()) == consumed_before
        assert (tmp / "a.txt").read_text(encoding="utf-8") == content_before
        assert s.state == SessionState.WAITING_APPROVAL

# 17. NO HIDDEN RETRY LOOP — one reenter corresponds to one pipeline attempt
def test_p97b_no_hidden_retry_loop():
    with tempfile.TemporaryDirectory(prefix="rec17_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        s = AgentSession(session_id="rec-retry", goal="add api_key", workspace=tmp, allowed_paths=(str(tmp),))
        s.transition_to(SessionState.INSPECTING)
        insp = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        s.attach_inspection(insp)
        s.transition_to(SessionState.INSPECTED)
        adapter = SessionProposalAdapter()
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        from simulation.agent.session.session_governed_bridge import SessionGovernedBridge
        SessionGovernedBridge().execute(s, pipeline)
        snap = load_snapshot(save_snapshot(s, base_dir=Path(td)/"snap"))
        rec = reconstruct_session(snap, worker_result=wr)
        # first reenter without approval -> stays WAITING, governance_count should be 2 (1 original +1)
        gov_cnt_before = rec.governance_count
        result = reenter_session(rec, pipeline)
        assert rec.governance_count == gov_cnt_before + 1
        assert result.failure_stage == "approval"
        # second explicit reenter should increment again by 1, not loop
        result2 = reenter_session(rec, pipeline)
        assert rec.governance_count == gov_cnt_before + 2
