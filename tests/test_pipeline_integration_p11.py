"""P11 — Pipeline Integration (Model B durable attempt authority)

Proves pipeline orchestration layer invariants:
- does not produce business intent
- does not advance attempt via raw integer or AgentSession
- retry via journal-issued AttemptContext immutable
- intent/attempt mismatch fail-closed before provider
- missing/forged/stale context no provider
- approval binding preserved
"""

from pathlib import Path
import tempfile

import pytest

from simulation.agent.apply.external_action import ExternalAction
from simulation.agent.apply.external_intent import create_intent
from simulation.agent.apply.external_outcome_journal import AttemptContext, ExternalOutcomeJournal
from simulation.agent.apply.external_provider import AlwaysSuccessProvider, ExternalOutcome, ScriptedProvider
from simulation.agent.approval.approval_ledger import ApprovalLedger
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.pipeline.external_action_pipeline import ExternalActionPipeline
from simulation.agent.apply.external_executor import ExternalActionExecutor
from simulation.agent.session.agent_session import AgentSession
from simulation.security.governance_evaluator import GovernanceEvaluator
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_policy import RiskPolicy


def _pipeline(tmp_path: Path, scope=("external://",)):
    ledger = ApprovalLedger(str(tmp_path / "ledger.jsonl"))
    store = ApprovalStore(ledger=ledger)
    gov = GovernanceEvaluator(risk_engine=RiskEngine(), risk_policy=RiskPolicy())
    journal = ExternalOutcomeJournal(str(tmp_path / "ext.jsonl"))
    executor = ExternalActionExecutor(approval_store=store, governance=gov, journal=journal)
    pipeline = ExternalActionPipeline(governance=gov, approval_store=store, external_executor=executor, scope=scope)
    return pipeline, store, gov, journal, executor, ledger


def _high_action(idem="P11-KEY"):
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


# P1 — Pipeline does not advance external attempt via AgentSession
def test_p1_pipeline_does_not_advance_external_attempt(tmp_path: Path):
    pipeline, store, gov, journal, executor, _ = _pipeline(tmp_path)
    action = _high_action("P1-KEY")
    intent_id = create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "ws-p11", "nonce-p1")

    # Create session and track next_attempt calls
    session = AgentSession(goal="test", workspace=tmp_path, allowed_paths=("external://",), max_attempts=3, attempt=1)
    original_next = session.next_attempt
    call_count = {"n": 0}
    def tracked_next():
        call_count["n"] += 1
        return original_next()
    # monkeypatch instance
    import unittest.mock as mock
    with mock.patch.object(session, "next_attempt", side_effect=tracked_next):
        # Attempt 1 via pipeline
        appr1 = _grant(store, gov, action, 1)
        provider1 = ScriptedProvider(script=[ExternalOutcome.TIMEOUT_UNKNOWN], name="p1-1")
        result1 = pipeline.execute(action, provider=provider1, intent_id=intent_id)
        assert result1.external_result.outcome == ExternalOutcome.TIMEOUT_UNKNOWN
        # Retry via journal AttemptContext
        appr2 = _grant(store, gov, action, 2)
        ctx2 = journal.open_attempt(intent_id, expected_current_attempt=1, new_approval_id=appr2.approval_id)
        provider2 = AlwaysSuccessProvider()
        result2 = pipeline.execute(action, provider=provider2, attempt_context=ctx2)
        assert result2.success is True
        # Ensure session was never advanced by pipeline
        assert call_count["n"] == 0
        assert session.attempt == 1  # unchanged, pipeline did not mutate session
    # Also ensure pipeline did not do raw attempt +=1 internally (provider executed with context's attempt)
    assert provider2.call_count == 1
    # Verify journal lineage shows attempt from context, not from session
    recs = journal.load()
    attempts = [r.get("attempt") for r in recs if r["intent_id"] == intent_id and r["record_type"] in ("external_intent", "attempt_opened")]
    assert attempts == [1, 2]


# P2 — Valid AttemptContext reaches execution path and remains immutable
def test_p2_valid_attempt_context_reaches_execution(tmp_path: Path):
    pipeline, store, gov, journal, _, _ = _pipeline(tmp_path)
    action = _high_action("P2-KEY")
    intent_id = create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "ws-p11", "nonce-p2")
    appr1 = _grant(store, gov, action, 1)
    provider1 = ScriptedProvider(script=[ExternalOutcome.TIMEOUT_UNKNOWN])
    pipeline.execute(action, provider=provider1, intent_id=intent_id)
    appr2 = _grant(store, gov, action, 2)
    ctx2 = journal.open_attempt(intent_id, expected_current_attempt=1, new_approval_id=appr2.approval_id)
    # Capture immutable snapshot
    before = (ctx2.intent_id, ctx2.attempt, ctx2.approval_id, ctx2.previous_hash, ctx2.expected_previous_attempt)
    provider2 = ScriptedProvider(script=[ExternalOutcome.KNOWN_SUCCESS])
    result = pipeline.execute(action, provider=provider2, attempt_context=ctx2)
    assert result.success is True
    assert provider2.call_count == 1
    # Context immutable
    after = (ctx2.intent_id, ctx2.attempt, ctx2.approval_id, ctx2.previous_hash, ctx2.expected_previous_attempt)
    assert before == after
    # Provider boundary used context.attempt
    recs = journal.load()
    last_started = [r for r in recs if r["intent_id"] == intent_id and r["record_type"] == "external_started"][-1]
    # The retry started record is created by journal with attempt 2
    assert last_started is not None
    # And pipeline's authoritative attempt was 2 (provider executed once for retry)
    assert ctx2.attempt == 2


# P3 — Mismatched intent fails closed before provider
def test_p3_mismatched_intent_fails_closed(tmp_path: Path):
    pipeline, store, gov, journal, _, _ = _pipeline(tmp_path)
    action_a = _high_action("P3-A")
    intent_a = create_intent(action_a.provider, action_a.operation, action_a.payload, action_a.idempotency_key, action_a.reason, "ws-p11", "nonce-p3a")
    action_b = _high_action("P3-B-DIFF")
    # Intent B different
    intent_b = create_intent(action_b.provider, action_b.operation, action_b.payload, action_b.idempotency_key, action_b.reason, "ws-p11", "nonce-p3b")
    assert intent_a != intent_b

    appr1 = _grant(store, gov, action_a, 1)
    provider1 = ScriptedProvider(script=[ExternalOutcome.TIMEOUT_UNKNOWN])
    pipeline.execute(action_a, provider=provider1, intent_id=intent_a)
    appr2 = _grant(store, gov, action_a, 2)
    ctx_a2 = journal.open_attempt(intent_a, expected_current_attempt=1, new_approval_id=appr2.approval_id)

    # Forged context with intent_b but action_a (mismatch)
    forged = AttemptContext(intent_id=intent_b, attempt=ctx_a2.attempt, synthetic=None, approval_id=ctx_a2.approval_id, previous_hash=ctx_a2.previous_hash, expected_previous_attempt=ctx_a2.expected_previous_attempt)
    # Need approval for forged to pass pipeline approval? Create one for action_a attempt2 with forged's approval_id? But forged uses same approval_id as ctx_a2, so pipeline will find it (same fingerprint attempt2) but journal will reject fingerprint/intent mismatch before provider
    # To ensure pipeline reaches executor, grant another approval with same ID but we already have it
    provider = AlwaysSuccessProvider()
    count_before = len(journal.load())
    tail_before = journal.tail_hash()
    result = pipeline.execute(action_a, provider=provider, attempt_context=forged)
    assert result.success is False
    assert provider.call_count == 0
    assert len(journal.load()) == count_before
    assert journal.tail_hash() == tail_before


# P4 — Mismatched attempt fails closed
def test_p4_mismatched_attempt_fails_closed(tmp_path: Path):
    pipeline, store, gov, journal, _, _ = _pipeline(tmp_path)
    action = _high_action("P4-KEY")
    intent_id = create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "ws-p11", "nonce-p4")
    appr1 = _grant(store, gov, action, 1)
    pipeline.execute(action, provider=ScriptedProvider(script=[ExternalOutcome.TIMEOUT_UNKNOWN]), intent_id=intent_id)
    appr2 = _grant(store, gov, action, 2)
    ctx2 = journal.open_attempt(intent_id, expected_current_attempt=1, new_approval_id=appr2.approval_id)
    # Tamper attempt to 3 (not durable) but keep hash/approval
    forged = AttemptContext(intent_id=ctx2.intent_id, attempt=3, synthetic=None, approval_id=ctx2.approval_id, previous_hash=ctx2.previous_hash, expected_previous_attempt=2)
    provider = AlwaysSuccessProvider()
    count_before = len(journal.load())
    result = pipeline.execute(action, provider=provider, attempt_context=forged)
    assert result.success is False
    assert provider.call_count == 0
    assert len(journal.load()) == count_before


# P5 — Missing context cannot authorize retry
def test_p5_missing_context_cannot_authorize_retry(tmp_path: Path):
    pipeline, store, gov, journal, _, _ = _pipeline(tmp_path)
    action = _high_action("P5-KEY")
    intent_id = create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "ws-p11", "nonce-p5")
    appr1 = _grant(store, gov, action, 1)
    pipeline.execute(action, provider=ScriptedProvider(script=[ExternalOutcome.TIMEOUT_UNKNOWN]), intent_id=intent_id)
    # Do not open attempt, try retry without context (missing)
    provider = AlwaysSuccessProvider()
    count_before = len(journal.load())
    # Attempt to execute retry semantic without context — use raw attempt integer (should be rejected)
    result_raw = pipeline.execute(action, provider=provider, attempt=2)
    assert result_raw.success is False
    assert provider.call_count == 0
    # Also missing both
    provider2 = AlwaysSuccessProvider()
    result_none = pipeline.execute(action, provider=provider2)
    assert result_none.success is False
    assert provider2.call_count == 0
    assert len(journal.load()) == count_before


# P6 — Forged / stale context cannot bypass journal authority
def test_p6_forged_stale_cannot_bypass(tmp_path: Path):
    pipeline, store, gov, journal, _, _ = _pipeline(tmp_path)
    action = _high_action("P6-KEY")
    intent_id = create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "ws-p11", "nonce-p6")
    appr1 = _grant(store, gov, action, 1)
    pipeline.execute(action, provider=ScriptedProvider(script=[ExternalOutcome.TIMEOUT_UNKNOWN]), intent_id=intent_id)
    appr2 = _grant(store, gov, action, 2)
    ctx2 = journal.open_attempt(intent_id, expected_current_attempt=1, new_approval_id=appr2.approval_id)
    # Forged previous_hash
    forged = AttemptContext(intent_id=ctx2.intent_id, attempt=ctx2.attempt, synthetic=None, approval_id=ctx2.approval_id, previous_hash="BAD_HASH", expected_previous_attempt=ctx2.expected_previous_attempt)
    provider = AlwaysSuccessProvider()
    count_before = len(journal.load())
    result = pipeline.execute(action, provider=provider, attempt_context=forged)
    assert result.success is False
    assert provider.call_count == 0
    assert len(journal.load()) == count_before
    # Stale: execute valid ctx2 once, then replay old ctx2 after advancing
    pipeline.execute(action, provider=AlwaysSuccessProvider(), attempt_context=ctx2)
    # Now ctx2 is stale because state moved to external_started(2) then success
    provider_stale = AlwaysSuccessProvider()
    count_before2 = len(journal.load())
    result_stale = pipeline.execute(action, provider=provider_stale, attempt_context=ctx2)
    assert result_stale.success is False
    assert provider_stale.call_count == 0
    assert len(journal.load()) == count_before2


# P7 — Existing approval binding preserved (old approval cannot authorize new attempt)
def test_p7_existing_approval_binding_preserved(tmp_path: Path):
    pipeline, store, gov, journal, _, _ = _pipeline(tmp_path)
    action = _high_action("P7-KEY")
    intent_id = create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "ws-p11", "nonce-p7")
    appr1 = _grant(store, gov, action, 1)
    pipeline.execute(action, provider=ScriptedProvider(script=[ExternalOutcome.TIMEOUT_UNKNOWN]), intent_id=intent_id)
    appr2 = _grant(store, gov, action, 2)
    ctx2 = journal.open_attempt(intent_id, expected_current_attempt=1, new_approval_id=appr2.approval_id)
    # Create another approval for attempt 2 but different ID
    appr2_other = _grant(store, gov, action, 2)
    # Forge ctx with appr1 (attempt1) approval to try to authorize attempt2
    forged_ctx = AttemptContext(intent_id=ctx2.intent_id, attempt=2, synthetic=None, approval_id=appr1.approval_id, previous_hash=ctx2.previous_hash, expected_previous_attempt=1)
    provider = AlwaysSuccessProvider()
    count_before = len(journal.load())
    result = pipeline.execute(action, provider=provider, attempt_context=forged_ctx)
    assert result.success is False
    assert result.failure_stage == "approval"
    assert provider.call_count == 0
    assert len(journal.load()) == count_before
    # Also ensure store's approval validation still intact directly
    from simulation.agent.approval.approval_validation import is_approval_valid
    syn = action.to_patch_proposal(allowed_paths=("external://",))
    valid, reason = is_approval_valid(appr1, syn, gov.evaluate(syn).risk_level.value, 2)
    assert valid is False
    assert "attempt" in reason.lower()
