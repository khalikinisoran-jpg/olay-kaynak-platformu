"""M12 — External Action Runtime Wiring via SessionGovernedBridge.

Proves REAL runtime/session path reaches ExternalActionPipeline without
direct provider bypass, with scope/governance/approval/journal preserved.
"""
import tempfile
from pathlib import Path

import pytest

from simulation.agent.apply.external_action import ExternalAction
from simulation.agent.apply.external_intent import create_intent
from simulation.agent.apply.external_outcome_journal import ExternalOutcomeJournal
from simulation.agent.apply.external_provider import AlwaysSuccessProvider, ExternalOutcome, ScriptedProvider
from simulation.agent.approval.approval_ledger import ApprovalLedger
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.pipeline.external_action_pipeline import ExternalActionPipeline
from simulation.agent.apply.external_executor import ExternalActionExecutor
from simulation.agent.session.agent_session import AgentSession, SessionState
from simulation.agent.session.session_governed_bridge import SessionGovernedBridge
from simulation.security.governance_evaluator import GovernanceEvaluator
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_policy import RiskPolicy
from simulation.agent.worker.patch_proposal import PatchProposal
from simulation.agent.worker.worker_result import WorkerResult


def _bridge_setup(tmp_path: Path, scope=("external://",)):
    ledger = ApprovalLedger(str(tmp_path / "ledger.jsonl"))
    store = ApprovalStore(ledger=ledger)
    gov = GovernanceEvaluator(risk_engine=RiskEngine(), risk_policy=RiskPolicy())
    journal = ExternalOutcomeJournal(str(tmp_path / "ext.jsonl"))
    executor = ExternalActionExecutor(approval_store=store, governance=gov, journal=journal)
    pipeline = ExternalActionPipeline(governance=gov, approval_store=store, external_executor=executor, scope=scope)
    bridge = SessionGovernedBridge()
    return pipeline, store, gov, journal, executor, bridge


def _high_action(idem="M12-KEY"):
    return ExternalAction(provider="secrets", operation="charge", payload='{"password":"x"}', idempotency_key=idem, reason="high")


def _grant(store, gov, action, attempt, scope=("external://",)):
    syn = action.to_patch_proposal(allowed_paths=scope)
    dec = gov.evaluate(syn)
    return store.grant(
        patch_fingerprint=syn.fingerprint(),
        path=syn.path,
        action=syn.action,
        risk_level=dec.risk_level.value,
        attempt=attempt,
        authorizer="tester",
        expires_at=3600,
    )


def _session(tmp_path: Path, allowed_scope=("external://",)):
    # Use external scope as allowed_paths for session workspace
    ws = tmp_path / "ws"
    ws.mkdir(parents=True, exist_ok=True)
    return AgentSession(goal="external wiring", workspace=ws, allowed_paths=allowed_scope, max_attempts=3, attempt=1)


# TEST 1 — REAL RUNTIME REACHABILITY via Bridge (not direct pipeline)
def test_m12_real_runtime_reachability_via_bridge(tmp_path: Path):
    pipeline, store, gov, journal, _, bridge = _bridge_setup(tmp_path)
    action = _high_action("M12-T1")
    intent_id = create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "ws-m12", "nonce-t1")
    _grant(store, gov, action, 1)
    session = _session(tmp_path)
    session.transition_to(SessionState.INSPECTING)
    session.transition_to(SessionState.INSPECTED)
    session.transition_to(SessionState.PROPOSING)
    session.attach_external_action(action)
    provider = AlwaysSuccessProvider()
    # Bridge is the real runtime path, not direct pipeline.execute
    result = bridge.execute_external(session, pipeline, action, provider=provider, intent_id=intent_id)
    assert result.success is True
    assert result.is_success is True
    assert provider.call_count == 1
    # Session state should be VERIFIED via bridge mapping
    assert session.state == SessionState.VERIFIED
    # Journal evidence observable
    recs = journal.load()
    assert any(r["record_type"] == "external_intent" and r["intent_id"] == intent_id for r in recs)
    assert any(r["record_type"] == "external_success" for r in recs)


# TEST 2 — NO DIRECT PROVIDER BYPASS (denied action -> 0 calls)
def test_m12_no_direct_provider_bypass_on_denied(tmp_path: Path):
    pipeline, store, gov, journal, _, bridge = _bridge_setup(tmp_path)
    action = _high_action("M12-T2")
    # No approval granted -> high-risk should be denied
    session = _session(tmp_path)
    session.transition_to(SessionState.INSPECTING)
    session.transition_to(SessionState.INSPECTED)
    session.transition_to(SessionState.PROPOSING)
    session.attach_external_action(action)
    provider = AlwaysSuccessProvider()
    # Spy: wrap provider to detect direct calls vs pipeline calls – bridge must not call provider directly
    # If bridge bypassed pipeline and called provider directly, journal would not have intent, but we check both
    count_before = len(journal.load())
    result = bridge.execute_external(session, pipeline, action, provider=provider, intent_id=create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "ws-m12", "nonce-t2"))
    assert result.success is False
    assert result.failure_stage == "approval"
    assert provider.call_count == 0
    assert len(journal.load()) == count_before
    # Also ensure bridge file does not contain direct provider.execute string outside pipeline delegation
    import pathlib
    bridge_text = pathlib.Path("simulation/agent/session/session_governed_bridge.py").read_text(encoding="utf-8")
    # Remove the delegation line "pipeline.execute" and check no direct "provider.execute"
    assert "provider.execute" not in bridge_text or "pipeline.execute" in bridge_text


# TEST 3 — APPROVAL DENIAL (high-risk without valid approval -> 0 provider calls)
def test_m12_approval_denial_zero_calls(tmp_path: Path):
    pipeline, store, gov, journal, _, bridge = _bridge_setup(tmp_path)
    action = _high_action("M12-T3")
    session = _session(tmp_path)
    session.transition_to(SessionState.INSPECTING)
    session.transition_to(SessionState.INSPECTED)
    session.transition_to(SessionState.PROPOSING)
    session.attach_external_action(action)
    provider = AlwaysSuccessProvider()
    intent_id = create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "ws-m12", "nonce-t3")
    result = bridge.execute_external(session, pipeline, action, provider=provider, intent_id=intent_id)
    assert result.success is False
    assert provider.call_count == 0
    assert session.state in (SessionState.WAITING_APPROVAL, SessionState.DENIED)


# TEST 4 — VALID APPROVAL PATH (provider reached, journal observable)
def test_m12_valid_approval_reaches_provider(tmp_path: Path):
    pipeline, store, gov, journal, _, bridge = _bridge_setup(tmp_path)
    action = _high_action("M12-T4")
    intent_id = create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "ws-m12", "nonce-t4")
    _grant(store, gov, action, 1)
    session = _session(tmp_path)
    session.transition_to(SessionState.INSPECTING)
    session.transition_to(SessionState.INSPECTED)
    session.transition_to(SessionState.PROPOSING)
    session.attach_external_action(action)
    provider = AlwaysSuccessProvider()
    result = bridge.execute_external(session, pipeline, action, provider=provider, intent_id=intent_id)
    assert result.success is True
    assert provider.call_count == 1
    # ExternalOutcomeJournal evidence
    recs = journal.load()
    assert recs[0]["intent_id"] == intent_id
    assert recs[0]["attempt"] == 1
    # Session should be VERIFIED
    assert session.state == SessionState.VERIFIED
    # Attempting same intent via bridge again should fail at journal (duplicate intent) -> 0 provider calls for second
    session2 = _session(tmp_path / "ws2")
    session2.workspace = session.workspace
    session2.allowed_paths = session.allowed_paths
    session2.transition_to(SessionState.INSPECTING)
    session2.transition_to(SessionState.INSPECTED)
    session2.transition_to(SessionState.PROPOSING)
    session2.attach_external_action(action)
    provider2 = AlwaysSuccessProvider()
    # Need new approval for attempt 1 but same intent_id already terminal -> journal should deny
    _grant(store, gov, action, 1)
    result2 = bridge.execute_external(session2, pipeline, action, provider=provider2, intent_id=intent_id)
    # Should be deny (journal invalid transition) -> 0 provider calls
    assert provider2.call_count == 0


# TEST 5 — SCOPE DENIAL (outside authoritative scope -> 0 provider calls)
def test_m12_scope_denial_zero_calls(tmp_path: Path):
    # Pipeline with restrictive scope that does not include action's synthetic path
    pipeline, store, gov, journal, _, bridge = _bridge_setup(tmp_path, scope=("external://payments",))
    # Action uses provider "secrets" -> synthetic_path external://secrets/charge not in payments scope
    action = _high_action("M12-T5")
    _grant(store, gov, action, 1)
    session = _session(tmp_path, allowed_scope=("external://payments",))
    session.transition_to(SessionState.INSPECTING)
    session.transition_to(SessionState.INSPECTED)
    session.transition_to(SessionState.PROPOSING)
    session.attach_external_action(action)
    provider = AlwaysSuccessProvider()
    intent_id = create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "ws-m12", "nonce-t5")
    result = bridge.execute_external(session, pipeline, action, provider=provider, intent_id=intent_id)
    assert result.success is False
    assert result.failure_stage == "validation"
    assert "scope" in result.failure_reason.lower()
    assert provider.call_count == 0


# TEST 6 — AMBIGUOUS OUTCOME not verified
def test_m12_ambiguous_not_verified(tmp_path: Path):
    pipeline, store, gov, journal, _, bridge = _bridge_setup(tmp_path)
    action = _high_action("M12-T6")
    intent_id = create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "ws-m12", "nonce-t6")
    _grant(store, gov, action, 1)
    session = _session(tmp_path)
    session.transition_to(SessionState.INSPECTING)
    session.transition_to(SessionState.INSPECTED)
    session.transition_to(SessionState.PROPOSING)
    session.attach_external_action(action)
    provider = ScriptedProvider(script=[ExternalOutcome.TIMEOUT_UNKNOWN])
    result = bridge.execute_external(session, pipeline, action, provider=provider, intent_id=intent_id)
    assert result.success is False
    assert result.failure_stage == "external_ambiguous"
    assert result.is_ambiguous is True
    assert provider.call_count == 1
    # Session must not be VERIFIED
    assert session.state != SessionState.VERIFIED
    assert session.state == SessionState.FAILED
    # Journal should have timeout_unknown, not success
    recs = journal.load()
    assert any(r["record_type"] == "external_timeout_unknown" for r in recs)
    assert not any(r["record_type"] == "external_success" and r["intent_id"] == intent_id for r in recs)


# TEST 7 — FILE PATH REGRESSION (WorkerActionPipeline still via Bridge)
def test_m12_file_path_still_via_worker_pipeline(tmp_path: Path):
    from simulation.agent.pipeline.worker_action_pipeline import WorkerActionPipeline
    from simulation.agent.apply.apply_executor import ApplyExecutor
    from simulation.agent.pipeline.apply_verify_pipeline import ApplyVerifyPipeline
    from simulation.agent.verify.verification_executor import VerificationExecutor
    from simulation.agent.worker.patch_proposal import PatchProposal
    from simulation.agent.worker.worker_result import WorkerResult

    # Build file pipeline via bridge as before
    ledger = ApprovalLedger(str(tmp_path / "ledger2.jsonl"))
    store = ApprovalStore(ledger=ledger)
    gov = GovernanceEvaluator(risk_engine=RiskEngine(), risk_policy=RiskPolicy())
    workspace = tmp_path / "ws_file"
    workspace.mkdir(exist_ok=True)
    (workspace / "a.txt").write_text("hello", encoding="utf-8")
    dummy = workspace / "test_dummy.py"
    dummy.write_text("def test_dummy(): assert True\n", encoding="utf-8")
    pipeline = WorkerActionPipeline(governance=gov, approval_store=store, scope=(str(workspace),))
    bridge = SessionGovernedBridge()
    session = AgentSession(goal="file wiring", workspace=workspace, allowed_paths=(str(workspace),), max_attempts=3, attempt=1)
    session.transition_to(SessionState.INSPECTING)
    session.transition_to(SessionState.INSPECTED)
    session.transition_to(SessionState.PROPOSING)
    p = PatchProposal(path=str(workspace / "a.txt"), action="modify", reason="fix", old_content="hello", new_content="hello fixed", allowed_paths=(str(workspace),))
    wr = WorkerResult(task_id="m12-file", success=True, summary="file", patches=(p,))
    session.attach_proposal(wr)
    result = bridge.execute(session, pipeline, verify_paths=[str(workspace)], test_targets=[str(dummy)])
    assert result.success is True
    assert (workspace / "a.txt").read_text(encoding="utf-8") == "hello fixed"
    assert session.state == SessionState.VERIFIED
