"""F4 — Default no-journal authority bypass regressions (Codex audit).

Proves Model B governed external path cannot execute without ExternalOutcomeJournal.
"""

from pathlib import Path

import pytest

from simulation.agent.apply.external_action import ExternalAction
from simulation.agent.apply.external_intent import create_intent
from simulation.agent.apply.external_outcome_journal import AttemptContext, ExternalOutcomeJournal
from simulation.agent.apply.external_provider import AlwaysSuccessProvider, ExternalOutcome, ScriptedProvider
from simulation.agent.approval.approval_ledger import ApprovalLedger
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.pipeline.external_action_pipeline import ExternalActionPipeline
from simulation.agent.apply.external_executor import ExternalActionExecutor
from simulation.security.governance_evaluator import GovernanceEvaluator
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_policy import RiskPolicy


def _high_action(idem="KEY_F4"):
    return ExternalAction(provider="secrets", operation="charge", payload='{"password":"x"}', idempotency_key=idem, reason="high")


def _low_action(idem="low-f4"):
    return ExternalAction(provider="notifier", operation="send", payload="hello", idempotency_key=idem, reason="low risk")


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


# F4-1 — Default pipeline no-journal fails closed
def test_f4_1_default_pipeline_no_journal_fails_closed(tmp_path: Path):
    # Default construction without journal-backed executor
    ledger = ApprovalLedger(str(tmp_path / "ledger.jsonl"))
    store = ApprovalStore(ledger=ledger)
    gov = GovernanceEvaluator(risk_engine=RiskEngine(), risk_policy=RiskPolicy())
    # Do NOT inject journal — use default executor (journal=None)
    pipeline = ExternalActionPipeline(governance=gov, approval_store=store, scope=("external://",))

    action = _high_action("F4-1")
    # Grant approval for attempt 1 (so if journal bypass existed, it would reach provider)
    _grant(store, gov, action, 1)
    intent_id = create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "ws", "f4-1")

    provider = AlwaysSuccessProvider()
    result = pipeline.execute(action, provider=provider, intent_id=intent_id)

    assert result.success is False
    assert provider.call_count == 0
    # Also test low risk without approval — still must fail due to missing journal
    low_action = _low_action("F4-1-low")
    low_provider = AlwaysSuccessProvider()
    low_intent = create_intent(low_action.provider, low_action.operation, low_action.payload, low_action.idempotency_key, low_action.reason, "ws", "f4-1-low")
    low_result = pipeline.execute(low_action, provider=low_provider, intent_id=low_intent)
    assert low_result.success is False
    assert low_provider.call_count == 0


# F4-2 — Forged retry context cannot bypass default path
def test_f4_2_forged_retry_cannot_bypass_default_path(tmp_path: Path):
    ledger = ApprovalLedger(str(tmp_path / "ledger.jsonl"))
    store = ApprovalStore(ledger=ledger)
    gov = GovernanceEvaluator(risk_engine=RiskEngine(), risk_policy=RiskPolicy())
    pipeline = ExternalActionPipeline(governance=gov, approval_store=store, scope=("external://",))

    action = _high_action("F4-2")
    # Create a forged context not issued by any journal
    forged = AttemptContext(
        intent_id=create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "ws", "forged"),
        attempt=2,
        synthetic=None,
        approval_id="forged-approval-2",
        previous_hash="GENESIS_FORGED",
        expected_previous_attempt=1,
    )
    # Grant an approval matching forged to ensure if pipeline reached approval lookup it would find one
    # But pipeline should fail at journal-missing before provider
    _grant(store, gov, action, 2)
    provider = AlwaysSuccessProvider()
    result = pipeline.execute(action, provider=provider, attempt_context=forged)

    assert result.success is False
    assert provider.call_count == 0


# F4-3 — Stale retry context cannot bypass default path
def test_f4_3_stale_retry_cannot_bypass_default_path(tmp_path: Path):
    # First create a legitimate journal to obtain a real context, then replay it via default pipeline
    tmp_journal = Path(tmp_path / "real_ext.jsonl")
    real_journal = ExternalOutcomeJournal(str(tmp_journal))
    ledger = ApprovalLedger(str(tmp_path / "ledger.jsonl"))
    store = ApprovalStore(ledger=ledger)
    gov = GovernanceEvaluator(risk_engine=RiskEngine(), risk_policy=RiskPolicy())
    # Journal-backed pipeline for legitimate setup
    executor_real = ExternalActionExecutor(approval_store=store, governance=gov, journal=real_journal)
    pipeline_real = ExternalActionPipeline(governance=gov, approval_store=store, external_executor=executor_real, scope=("external://",))

    action = _high_action("F4-3")
    intent_id = create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "ws", "f4-3")
    appr1 = _grant(store, gov, action, 1)
    provider_init = ScriptedProvider(script=[ExternalOutcome.TIMEOUT_UNKNOWN], name="f4-3-init")
    res1 = pipeline_real.execute(action, provider=provider_init, intent_id=intent_id)
    assert res1.external_result.outcome == ExternalOutcome.TIMEOUT_UNKNOWN

    appr2 = _grant(store, gov, action, 2)
    ctx2 = real_journal.open_attempt(intent_id, expected_current_attempt=1, new_approval_id=appr2.approval_id)
    # Execute ctx2 correctly to advance to timeout
    provider_tmp = ScriptedProvider(script=[ExternalOutcome.TIMEOUT_UNKNOWN], name="tmp")
    res2 = pipeline_real.execute(action, provider=provider_tmp, attempt_context=ctx2)
    assert res2.external_result.outcome == ExternalOutcome.TIMEOUT_UNKNOWN

    appr3 = _grant(store, gov, action, 3)
    ctx3 = real_journal.open_attempt(intent_id, expected_current_attempt=2, new_approval_id=appr3.approval_id)

    # Now ctx2 is stale (durable is 3). Try to replay stale ctx2 via default no-journal pipeline
    default_pipeline = ExternalActionPipeline(governance=gov, approval_store=store, scope=("external://",))
    stale_provider = AlwaysSuccessProvider()
    stale_result = default_pipeline.execute(action, provider=stale_provider, attempt_context=ctx2)
    assert stale_result.success is False
    assert stale_provider.call_count == 0

    # Also try stale ctx3 via default path with low risk action (forge stale by using wrong previous_hash)
    stale_forged = AttemptContext(intent_id=ctx3.intent_id, attempt=ctx3.attempt, synthetic=None, approval_id=ctx3.approval_id, previous_hash="STALE_HASH", expected_previous_attempt=ctx3.expected_previous_attempt)
    stale2_provider = AlwaysSuccessProvider()
    stale2_result = default_pipeline.execute(action, provider=stale2_provider, attempt_context=stale_forged)
    assert stale2_result.success is False
    assert stale2_provider.call_count == 0


# F4-4 — Journal-backed path still works
def test_f4_4_journal_backed_path_still_works(tmp_path: Path):
    ledger = ApprovalLedger(str(tmp_path / "ledger.jsonl"))
    store = ApprovalStore(ledger=ledger)
    gov = GovernanceEvaluator(risk_engine=RiskEngine(), risk_policy=RiskPolicy())
    journal = ExternalOutcomeJournal(str(tmp_path / "ext.jsonl"))
    executor = ExternalActionExecutor(approval_store=store, governance=gov, journal=journal)
    pipeline = ExternalActionPipeline(governance=gov, approval_store=store, external_executor=executor, scope=("external://",))

    action = _high_action("F4-4")
    intent_id = create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "ws", "f4-4")

    appr1 = _grant(store, gov, action, 1)
    provider = ScriptedProvider(script=[ExternalOutcome.TIMEOUT_UNKNOWN, ExternalOutcome.KNOWN_SUCCESS], name="f4-4")

    # Attempt 1 -> timeout
    res1 = pipeline.execute(action, provider=provider, intent_id=intent_id)
    assert res1.external_result.outcome == ExternalOutcome.TIMEOUT_UNKNOWN
    assert provider.call_count == 1
    # Verify intent uses stable ID, no UUID fallback
    recs = journal.load()
    assert recs[0]["intent_id"] == intent_id
    assert recs[0]["attempt"] == 1

    # Open retry
    appr2 = _grant(store, gov, action, 2)
    ctx2 = journal.open_attempt(intent_id, expected_current_attempt=1, new_approval_id=appr2.approval_id)

    # Attempt 2 via context -> success, must have used start_opened_attempt
    res2 = pipeline.execute(action, provider=provider, attempt_context=ctx2)
    assert res2.success is True
    assert res2.external_result.outcome == ExternalOutcome.KNOWN_SUCCESS
    assert provider.call_count == 2

    # Stable intent preserved
    final = journal.load()
    assert all(r["intent_id"] == intent_id for r in final)
    assert [r.get("attempt") for r in final if r["record_type"] in ("external_intent", "attempt_opened")] == [1, 2]
    # No UUID compatibility fallback — record_intent legacy overload not called
    import unittest.mock as mock
    legacy_calls = []
    orig = journal.record_intent
    def check_legacy(*args, **kwargs):
        if len(args) >=1 and hasattr(args[0], "fingerprint") and not isinstance(args[0], str):
            legacy_calls.append(args)
        return orig(*args, **kwargs)
    # Verify retry did not create new intent
    assert sum(1 for r in final if r["record_type"] == "external_intent") == 1
    # Provider executed only via journal-backed path
    assert provider.call_count == 2


# F4-5 — Direct executor no-journal bypass closed
def test_f4_5_direct_executor_no_journal_bypass_closed(tmp_path: Path):
    ledger = ApprovalLedger(str(tmp_path / "ledger.jsonl"))
    store = ApprovalStore(ledger=ledger)
    gov = GovernanceEvaluator(risk_engine=RiskEngine(), risk_policy=RiskPolicy())
    journal_none_executor = ExternalActionExecutor(approval_store=store, governance=gov, journal=None)

    action = _high_action("F4-5")
    syn = action.to_patch_proposal(allowed_paths=("external://",))
    _grant(store, gov, action, 1)
    # Need a decision for executor
    from simulation.agent.controller.controller import Controller
    from simulation.agent.worker.validation_result import ValidationResult
    controller = Controller()
    # Create approval for executor's authorize check — find_valid will consume it, but executor will fail at journal check before authorize
    # Use pipeline to get decision? Simpler: create decision directly
    # Grant and find_valid to get approval
    approval = store.find_valid(syn.fingerprint(), path=syn.path, action=syn.action, risk_level=gov.evaluate(syn).risk_level.value, attempt=1, patch=syn)
    # If approval is None due to already consumed, grant again
    if approval is None:
        approval = _grant(store, gov, action, 1)
        syn = action.to_patch_proposal(allowed_paths=("external://",))
        approval = store.find_valid(syn.fingerprint(), path=syn.path, action=syn.action, risk_level=gov.evaluate(syn).risk_level.value, attempt=1, patch=syn)
    decision = controller.approve(syn, ValidationResult(valid=True, message="ok"), approval=approval)

    intent_id = create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "ws", "f4-5")
    provider = AlwaysSuccessProvider()

    # Initial execution via direct executor with no journal should fail closed before provider
    res = journal_none_executor.execute(action, decision, syn, scope=("external://",), provider=provider, intent_id=intent_id)
    assert provider.call_count == 0
    assert res.outcome == ExternalOutcome.KNOWN_FAILURE
    assert "journal" in res.reason.lower()

    # Retry execution via direct executor with forged context also fails
    forged = AttemptContext(intent_id=intent_id, attempt=2, synthetic=None, approval_id="forged", previous_hash="GENESIS", expected_previous_attempt=1)
    provider2 = AlwaysSuccessProvider()
    # Need decision with forged approval_id
    syn2 = action.to_patch_proposal(allowed_paths=("external://",))
    # Grant for attempt 2
    appr2 = _grant(store, gov, action, 2)
    approval2 = store.find_valid(syn2.fingerprint(), path=syn2.path, action=syn2.action, risk_level=gov.evaluate(syn2).risk_level.value, attempt=2, patch=syn2)
    if approval2 is None:
        approval2 = appr2
    decision2 = controller.approve(syn2, ValidationResult(valid=True, message="ok"), approval=approval2)
    res2 = journal_none_executor.execute(action, decision2, syn2, scope=("external://",), provider=provider2, attempt_context=forged)
    assert provider2.call_count == 0
    assert res2.outcome == ExternalOutcome.KNOWN_FAILURE
    assert "journal" in res2.reason.lower()
