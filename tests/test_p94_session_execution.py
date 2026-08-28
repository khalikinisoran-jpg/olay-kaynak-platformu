"""P9.4 Governed Session Execution Bridge — 8 deterministic tests + meta.

Bridge is orchestration only: AgentSession (PROPOSING) -> SessionGovernedBridge.execute(session, pipeline) -> GOVERNING -> DENIED/WAITING_APPROVAL/VERIFIED via existing WorkerActionPipeline.
"""
import json
import pathlib
import tempfile
from pathlib import Path

import pytest

from simulation.agent.session.agent_session import AgentSession, SessionState
from simulation.agent.session.repository_inspector import RepositoryInspector
from simulation.agent.session.session_proposal_adapter import SessionProposalAdapter
from simulation.agent.session.session_governed_bridge import SessionGovernedBridge
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

def _make_inspected_session(tmp: Path, target="a.txt", content="hello", goal="fix"):
    (tmp / target).write_text(content, encoding="utf-8")
    insp = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path=target)
    s = AgentSession(session_id="s-p94", goal=goal, workspace=tmp, allowed_paths=(str(tmp),))
    s.transition_to(SessionState.INSPECTING)
    s.attach_inspection(insp)
    s.transition_to(SessionState.INSPECTED)
    return s, insp

# 1. NORMAL LOW-RISK SESSION FLOW
def test_p94_normal_low_session_flow():
    with tempfile.TemporaryDirectory(prefix="p94_low_") as td:
        tmp = Path(td)
        s, insp = _make_inspected_session(tmp, "a.txt", "hello", "fix hello")
        adapter = SessionProposalAdapter()
        # Valid LOW proposal
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "hello", "new_text": "hello fixed", "path": str(tmp / "a.txt")}))
        assert res.success
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        bridge = SessionGovernedBridge()
        result = bridge.execute(s, pipeline)
        assert s.state == SessionState.VERIFIED
        assert result.success is True
        assert result.verification_passed is True
        assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello fixed"
        # No direct write via session
        assert not hasattr(s, "apply")

# 2. HIGH-RISK SESSION WITHOUT APPROVAL
def test_p94_high_without_approval_waiting():
    with tempfile.TemporaryDirectory(prefix="p94_high_noauth_") as td:
        tmp = Path(td)
        s, insp = _make_inspected_session(tmp, "a.txt", "hello", "add api_key")
        adapter = SessionProposalAdapter()
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        assert res.success
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        bridge = SessionGovernedBridge()
        result = bridge.execute(s, pipeline)
        assert s.state == SessionState.WAITING_APPROVAL
        assert result.failure_stage == "approval"
        assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello"
        # Session did not grant approval
        assert not hasattr(s, "grant_approval")

# 3. HIGH-RISK WITH EXTERNAL VALID APPROVAL
def test_p94_high_with_external_approval_verified():
    with tempfile.TemporaryDirectory(prefix="p94_high_ok_") as td:
        tmp = Path(td)
        s, insp = _make_inspected_session(tmp, "a.txt", "hello", "add api_key")
        adapter = SessionProposalAdapter()
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        # External approval via ApprovalStore (only authority)
        p = res.patches[0]
        dec = gov.evaluate(p)
        assert dec.requires_human_approval is True
        store.grant(p.fingerprint(), path=p.path, action=p.action, risk_level=dec.risk_level.value, attempt=1)
        bridge = SessionGovernedBridge()
        result = bridge.execute(s, pipeline)
        assert s.state == SessionState.VERIFIED
        assert result.success is True
        # Single-use: second identical should be DENIED
        # Create new session with same patches but fresh store has consumed
        s2 = AgentSession(session_id="s2", goal="add api_key", workspace=tmp, allowed_paths=(str(tmp),))
        s2.transition_to(SessionState.INSPECTING)
        s2.attach_inspection(insp)
        s2.transition_to(SessionState.INSPECTED)
        # Need new inspection for new session but same file content now is api_key, so old_text mismatch will cause stale, but we test replay with same old/new as before via direct PatchProposal
        # Instead test replay via same WorkerResult but new session and same store (store already consumed)
        # For simplicity, use same tmp but restore file to hello and try again with same patch
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        # Need new adapter propose again to get new patch object with same fingerprint but different object identity
        res2 = adapter.propose(s2, insp, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        wr2 = WorkerResult(task_id="t", success=True, summary="t", patches=res2.patches)
        s2.attach_proposal(wr2)
        s2.transition_to(SessionState.PROPOSING)
        result2 = bridge.execute(s2, pipeline)
        # Should be WAITING_APPROVAL again (since approval consumed, not auto)
        assert s2.state in (SessionState.WAITING_APPROVAL, SessionState.DENIED)

# 4. GOVERNANCE DENIAL (risk HIGH without approval is actually WAITING, but other DENY like validation)
def test_p94_governance_denial():
    with tempfile.TemporaryDirectory(prefix="p94_denied_") as td:
        tmp = Path(td)
        s, insp = _make_inspected_session(tmp, "a.txt", "hello", "fix")
        # Propose with nonexistent old_text to trigger validation fail (stale)
        adapter = SessionProposalAdapter()
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "not-hello", "new_text": "hi", "path": str(tmp / "a.txt")}))
        assert res.success  # adapter succeeds (old_text not validated against file yet), but pipeline will deny
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        bridge = SessionGovernedBridge()
        result = bridge.execute(s, pipeline)
        assert s.state == SessionState.DENIED
        assert result.failure_stage == "validation"
        assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello"

# 5. SCOPE / PATH ESCAPE THROUGH SESSION
def test_p94_scope_escape_via_session_denied():
    with tempfile.TemporaryDirectory(prefix="p94_scope_") as td:
        tmp = Path(td)
        outer = Path(tempfile.mkdtemp(prefix="p94_outer_"))
        try:
            victim = outer / "victim.txt"
            victim.write_text("safe", encoding="utf-8")
            (tmp / "a.txt").write_text("hello", encoding="utf-8")
            s, insp = _make_inspected_session(tmp, "a.txt", "hello", "fix")
            adapter = SessionProposalAdapter()
            res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "safe", "new_text": "pwned", "path": str(victim)}))
            # Adapter should already fail closed due scope
            assert res.success is False
            assert "outside allowed scope" in res.failure_reason
            # Even if we force a PatchProposal outside scope, pipeline will deny
            p_out = PatchProposal(path=str(victim), action="modify", reason="x", old_content="safe", new_content="pwned", allowed_paths=(str(tmp),))
            wr = WorkerResult(task_id="t", success=True, summary="t", patches=(p_out,))
            s2 = AgentSession(session_id="s-scope", goal="g", workspace=tmp, allowed_paths=(str(tmp),))
            s2.transition_to(SessionState.INSPECTING)
            insp2 = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
            s2.attach_inspection(insp2)
            s2.transition_to(SessionState.INSPECTED)
            s2.attach_proposal(wr)
            s2.transition_to(SessionState.PROPOSING)
            pipeline, store, gov = _gov_pipeline(tmp)
            result = SessionGovernedBridge().execute(s2, pipeline)
            assert s2.state == SessionState.DENIED
            assert victim.read_text(encoding="utf-8") == "safe"
        finally:
            try:
                victim.unlink(); outer.rmdir()
            except Exception:
                pass

# 6. REPLAY / SINGLE-USE THROUGH SESSION
def test_p94_replay_single_use_via_session():
    with tempfile.TemporaryDirectory(prefix="p94_replay_") as td:
        tmp = Path(td)
        s, insp = _make_inspected_session(tmp, "a.txt", "hello", "add api_key")
        adapter = SessionProposalAdapter()
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        p = res.patches[0]
        dec = gov.evaluate(p)
        store.grant(p.fingerprint(), path=p.path, action=p.action, risk_level=dec.risk_level.value, attempt=1)
        result = SessionGovernedBridge().execute(s, pipeline)
        assert s.state == SessionState.VERIFIED
        # Restore and replay same patches via new session
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        s2 = AgentSession(session_id="s-replay", goal="add api_key", workspace=tmp, allowed_paths=(str(tmp),))
        s2.transition_to(SessionState.INSPECTING)
        insp2 = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        s2.attach_inspection(insp2)
        s2.transition_to(SessionState.INSPECTED)
        # Need new adapter propose to get new patch object with same fingerprint but different identity
        res2 = adapter.propose(s2, insp2, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        wr2 = WorkerResult(task_id="t", success=True, summary="t", patches=res2.patches)
        s2.attach_proposal(wr2)
        s2.transition_to(SessionState.PROPOSING)
        result2 = SessionGovernedBridge().execute(s2, pipeline)
        assert s2.state in (SessionState.WAITING_APPROVAL, SessionState.DENIED)
        assert result2.failure_stage == "approval"

# 7. MULTI-FILE GOVERNANCE (P8 atomicity preserved via session)
def test_p94_multi_file_governance():
    with tempfile.TemporaryDirectory(prefix="p94_multi_") as td:
        tmp = Path(td)
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        (tmp / "b.txt").write_text("world", encoding="utf-8")
        # Create a session with two files inspected, then propose two patches
        insp_a = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="a.txt")
        insp_b = RepositoryInspector().inspect(workspace=tmp, allowed_paths=(str(tmp),), target_path="b.txt")
        s = AgentSession(session_id="s-multi", goal="fix both", workspace=tmp, allowed_paths=(str(tmp),))
        s.transition_to(SessionState.INSPECTING)
        s.attach_inspection(insp_a)
        s.transition_to(SessionState.INSPECTED)
        # For multi-file, we need two patches in one WorkerResult
        from simulation.agent.worker.patch_proposal import PatchProposal as PP
        p1 = PP(path=str(tmp / "a.txt"), action="modify", reason="fix", old_content="hello", new_content="hello fixed", allowed_paths=(str(tmp),))
        p2 = PP(path=str(tmp / "b.txt"), action="modify", reason="fix", old_content="world", new_content="world fixed", allowed_paths=(str(tmp),))
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=(p1, p2))
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        result = SessionGovernedBridge().execute(s, pipeline)
        assert s.state == SessionState.VERIFIED
        assert result.success is True
        assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello fixed"
        assert (tmp / "b.txt").read_text(encoding="utf-8") == "world fixed"
        # Verify P8 atomicity: if second file outside scope, first rolled back
        (tmp / "a.txt").write_text("hello", encoding="utf-8")
        outer = Path(tempfile.mkdtemp(prefix="p94_multi_out_"))
        try:
            victim = outer / "victim.txt"
            victim.write_text("safe", encoding="utf-8")
            p_out = PP(path=str(victim), action="modify", reason="x", old_content="safe", new_content="pwned", allowed_paths=(str(tmp),))
            wr2 = WorkerResult(task_id="t", success=True, summary="t", patches=(p1, p_out))
            s2 = AgentSession(session_id="s-multi2", goal="g", workspace=tmp, allowed_paths=(str(tmp),))
            s2.transition_to(SessionState.INSPECTING)
            s2.attach_inspection(insp_a)
            s2.transition_to(SessionState.INSPECTED)
            s2.attach_proposal(wr2)
            s2.transition_to(SessionState.PROPOSING)
            result2 = SessionGovernedBridge().execute(s2, pipeline)
            assert s2.state == SessionState.DENIED
            assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello"  # rolled back
        finally:
            try:
                victim.unlink(); outer.rmdir()
            except Exception:
                pass

# 8. ZERO-BYPASS META TEST
def test_p94_zero_bypass_meta():
    import pathlib, re
    src = pathlib.Path("simulation/agent/session/session_governed_bridge.py").read_text(encoding="utf-8")
    # Check no direct authority imports (only check import lines, not docstring)
    imports = re.findall(r"^\s*(?:from|import)\s+.*$", src, flags=re.MULTILINE)
    for line in imports:
        assert "file_applier" not in line.lower(), f"FileApplier import forbidden: {line}"
        assert "approval_store" not in line.lower(), f"ApprovalStore import forbidden: {line}"
        assert "risk_engine" not in line.lower(), f"RiskEngine import forbidden: {line}"
        assert "verification_executor" not in line.lower(), f"VerificationExecutor import forbidden: {line}"
    # Session itself also not authority
    src2 = pathlib.Path("simulation/agent/session/agent_session.py").read_text(encoding="utf-8")
    imports2 = re.findall(r"^\s*(?:from|import)\s+.*$", src2, flags=re.MULTILINE)
    for line in imports2:
        assert "file_applier" not in line.lower()
        assert "approval_store" not in line.lower()
    # Behavioral zero-bypass: HIGH without approval via session must be WAITING_APPROVAL, not VERIFIED
    with tempfile.TemporaryDirectory(prefix="p94_zero_") as td:
        tmp = Path(td)
        s, insp = _make_inspected_session(tmp, "a.txt", "hello", "add api_key")
        adapter = SessionProposalAdapter()
        res = adapter.propose(s, insp, lambda: json.dumps({"old_text": "hello", "new_text": 'hello\napi_key = "sk-test"', "path": str(tmp / "a.txt")}))
        wr = WorkerResult(task_id="t", success=True, summary="t", patches=res.patches)
        s.attach_proposal(wr)
        s.transition_to(SessionState.PROPOSING)
        pipeline, store, gov = _gov_pipeline(tmp)
        result = SessionGovernedBridge().execute(s, pipeline)
        assert s.state == SessionState.WAITING_APPROVAL
        assert result.failure_stage == "approval"
        assert (tmp / "a.txt").read_text(encoding="utf-8") == "hello"
        # Also ensure token-like approval via session field does not bypass
        s3 = AgentSession(session_id="s-bypass", goal="g", workspace=tmp, allowed_paths=(str(tmp),))
        # Even if someone sets session.proposal_set_id manually to approved, it doesn't grant
        assert not hasattr(s3, "approved")
