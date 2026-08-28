"""External Action Spike — focused tests E1–E8 (P10.3-R1) migrated to Model B P10.3.

Deterministic, no network, no secrets. Proves governed ambiguous-result
foundation without assuming provider reconciliation.
Migrated to frozen Model B execution authority: intent_id / AttemptContext.
"""

import hashlib
from pathlib import Path

import pytest

from simulation.agent.apply.external_action import ExternalAction
from simulation.agent.apply.external_executor import ExternalActionExecutor
from simulation.agent.apply.external_intent import create_intent
from simulation.agent.apply.external_outcome_journal import ExternalOutcomeJournal
from simulation.agent.apply.external_provider import (
    AlwaysFailureProvider,
    AlwaysSuccessProvider,
    AmbiguousProvider,
    ExternalOutcome,
    NoLookupProvider,
    ScriptedProvider,
    TimeoutProvider,
)
from simulation.agent.approval.approval_ledger import ApprovalLedger
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.pipeline.external_action_pipeline import ExternalActionPipeline
from simulation.agent.recovery.external_reconciliation import ExternalReconciliationEngine
from simulation.security.governance_evaluator import GovernanceEvaluator
from simulation.security.risk_engine import RiskEngine
from simulation.security.risk_policy import RiskPolicy


def _governed_pipeline(tmp_path: Path, scope=("external://",), journal=None):
    ledger_path = tmp_path / "ledger.jsonl"
    ledger = ApprovalLedger(str(ledger_path))
    store = ApprovalStore(ledger=ledger)
    gov = GovernanceEvaluator(risk_engine=RiskEngine(), risk_policy=RiskPolicy())
    if journal is None:
        journal = ExternalOutcomeJournal(str(tmp_path / "ext_journal.jsonl"))
    executor = ExternalActionExecutor(approval_store=store, governance=gov, journal=journal)
    pipeline = ExternalActionPipeline(
        governance=gov,
        approval_store=store,
        external_executor=executor,
        scope=scope,
    )
    return pipeline, store, gov, journal, executor


def _high_action(idem="idem-1"):
    return ExternalAction(
        provider="secrets",
        operation="charge",
        payload='{"password": "x"}',
        idempotency_key=idem,
        reason="high risk external",
    )


def _low_action(idem="idem-low"):
    return ExternalAction(
        provider="notifier",
        operation="send",
        payload="hello",
        idempotency_key=idem,
        reason="low risk",
    )


def _intent_for(action: ExternalAction, nonce: str, workspace: str = "spike"):
    return create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, workspace, nonce)


def _grant_for_action(store: ApprovalStore, action: ExternalAction, gov, scope=("external://",), attempt=1):
    synthetic = action.to_patch_proposal(allowed_paths=scope)
    decision = gov.evaluate(synthetic)
    return store.grant(
        patch_fingerprint=synthetic.fingerprint(),
        path=synthetic.path,
        action=synthetic.action,
        risk_level=decision.risk_level.value,
        attempt=attempt,
        authorizer="tester",
        expires_at=3600,
    ), decision, synthetic


# E1 — Known success
def test_e1_known_success(tmp_path: Path):
    pipeline, store, gov, journal, executor = _governed_pipeline(tmp_path)
    action = _high_action("e1-idem")
    grant, decision, synthetic = _grant_for_action(store, action, gov, scope=("external://",), attempt=1)
    assert grant is not None

    provider = AlwaysSuccessProvider()
    intent_id = _intent_for(action, "e1")
    result = pipeline.execute(action, provider=provider, intent_id=intent_id)

    assert result.success is True
    assert result.external_result is not None
    assert result.external_result.outcome == ExternalOutcome.KNOWN_SUCCESS
    assert result.external_result.success is True
    assert result.external_result.is_known is True
    assert result.external_result.is_ambiguous is False
    assert provider.call_count == 1
    assert provider.calls[0].fingerprint() == action.fingerprint()
    records = journal.load()
    types = [r["record_type"] for r in records]
    assert types == ["external_intent", "external_started", "external_success"]
    synthetic2 = action.to_patch_proposal(allowed_paths=("external://",))
    again = store.find_valid(
        synthetic2.fingerprint(),
        path=synthetic2.path,
        action=synthetic2.action,
        risk_level=decision.risk_level.value,
        attempt=1,
        patch=synthetic2,
    )
    assert again is None
    assert decision.requires_human_approval is True


# E2 — Known explicit failure
def test_e2_known_failure(tmp_path: Path):
    pipeline, store, gov, journal, _ = _governed_pipeline(tmp_path)
    action = _high_action("e2-idem")
    grant, decision, _ = _grant_for_action(store, action, gov, scope=("external://",), attempt=1)

    provider = AlwaysFailureProvider()
    intent_id = _intent_for(action, "e2")
    result = pipeline.execute(action, provider=provider, intent_id=intent_id)

    assert result.success is False
    assert result.failure_stage == "external"
    assert result.external_result.outcome == ExternalOutcome.KNOWN_FAILURE
    assert result.external_result.success is False
    assert result.external_result.is_known is True
    assert provider.call_count == 1
    records = journal.load()
    types = [r["record_type"] for r in records]
    assert types == ["external_intent", "external_started", "external_failed"]
    assert result.is_ambiguous is False


# E3 — Timeout unknown
def test_e3_timeout_unknown(tmp_path: Path):
    pipeline, store, gov, journal, _ = _governed_pipeline(tmp_path)
    action = _high_action("e3-idem")
    _grant_for_action(store, action, gov, scope=("external://",), attempt=1)

    provider = TimeoutProvider()
    intent_id = _intent_for(action, "e3")
    result = pipeline.execute(action, provider=provider, intent_id=intent_id)

    assert result.success is False
    assert result.external_result.outcome == ExternalOutcome.TIMEOUT_UNKNOWN
    assert result.external_result.is_ambiguous is True
    assert result.is_ambiguous is True
    assert result.failure_stage == "external_ambiguous"
    assert result.external_result.success is False
    assert provider.call_count == 1
    records = journal.load()
    types = [r["record_type"] for r in records]
    assert types == ["external_intent", "external_started", "external_timeout_unknown"]
    assert provider.call_count == 1


# E4 — May have executed / response lost (ambiguous)
def test_e4_ambiguous_unknown(tmp_path: Path):
    pipeline, store, gov, journal, _ = _governed_pipeline(tmp_path)
    action = _high_action("e4-idem")
    _grant_for_action(store, action, gov, scope=("external://",), attempt=1)

    provider = AmbiguousProvider()
    intent_id = _intent_for(action, "e4")
    result = pipeline.execute(action, provider=provider, intent_id=intent_id)

    assert result.success is False
    assert result.external_result.outcome == ExternalOutcome.AMBIGUOUS_UNKNOWN
    assert result.external_result.is_ambiguous is True
    assert result.is_ambiguous is True
    assert result.failure_stage == "external_ambiguous"
    records = journal.load()
    types = [r["record_type"] for r in records]
    assert types == ["external_intent", "external_started", "external_ambiguous_unknown"]
    engine = ExternalReconciliationEngine(journal)
    report = engine.detect()
    assert len(report.ambiguous_intents) == 1
    assert report.ambiguous == 1
    assert provider.call_count == 1


# E5 — No provider status lookup
def test_e5_no_lookup_provider(tmp_path: Path):
    pipeline, store, gov, journal, _ = _governed_pipeline(tmp_path)
    action = _high_action("e5-idem")
    _grant_for_action(store, action, gov, scope=("external://",), attempt=1)

    provider = NoLookupProvider(script=[ExternalOutcome.TIMEOUT_UNKNOWN])
    assert not hasattr(provider, "reconcile")

    intent_id = _intent_for(action, "e5")
    result = pipeline.execute(action, provider=provider, intent_id=intent_id)

    assert result.external_result.outcome == ExternalOutcome.TIMEOUT_UNKNOWN
    assert result.is_ambiguous is True
    before = journal.load()
    engine = ExternalReconciliationEngine(journal)
    report = engine.detect()
    after = journal.load()
    assert before == after
    assert report.ambiguous == 1
    assert report.success == 0 and report.failed == 0
    assert provider.call_count == 1


# E6 — Recovery after ambiguous (detect-only)
def test_e6_recovery_after_ambiguous(tmp_path: Path):
    pipeline, store, gov, journal, _ = _governed_pipeline(tmp_path)
    action = _high_action("e6-idem")
    _grant_for_action(store, action, gov, scope=("external://",), attempt=1)
    provider = AmbiguousProvider()
    intent_id = _intent_for(action, "e6")
    result = pipeline.execute(action, provider=provider, intent_id=intent_id)
    assert result.is_ambiguous is True
    intent_count = provider.call_count
    assert intent_count == 1

    journal2 = ExternalOutcomeJournal(str(tmp_path / "ext_journal.jsonl"))
    engine = ExternalReconciliationEngine(journal2)
    report = engine.detect()

    assert report.ambiguous == 1
    assert report.total_intents == 1
    assert len(report.orphaned_intents) == 0
    assert provider.call_count == 1

    records = journal2.load()
    assert records[-1]["record_type"] == "external_ambiguous_unknown"


# E7 — Approval reuse negative (ambiguous does not reopen authority)
def test_e7_approval_reuse_denied_after_ambiguous(tmp_path: Path):
    pipeline, store, gov, journal, _ = _governed_pipeline(tmp_path)
    action = _high_action("e7-idem")
    grant, decision, synthetic = _grant_for_action(store, action, gov, scope=("external://",), attempt=1)

    provider = TimeoutProvider()
    intent_id = _intent_for(action, "e7")
    result1 = pipeline.execute(action, provider=provider, intent_id=intent_id)
    assert result1.is_ambiguous is True
    assert provider.call_count == 1

    # Reuse same intent_id with same attempt 1 — approval already consumed -> approval denial before journal duplicate
    provider2 = AlwaysSuccessProvider()
    # Use new nonce? But to test approval single-use we reuse same intent_id (same business op) — pipeline denies at approval stage
    # The intent_id is same as first; pipeline will fail at approval before journal duplicate matters because approval consumed
    # To keep deterministic, we reuse same intent_id
    result2 = pipeline.execute(action, provider=provider2, intent_id=intent_id)
    assert result2.success is False
    # Could be approval (approval consumed) — our pipeline denies at approval stage before executor journal duplicate
    assert result2.failure_stage == "approval"
    assert result2.external_result is None or result2.external_result.outcome != ExternalOutcome.KNOWN_SUCCESS
    assert provider2.call_count == 0
    # Raw integer attempt 2 bypass must be rejected at validation (not via approval)
    provider3 = AlwaysSuccessProvider()
    result3 = pipeline.execute(action, provider=provider3, attempt=2)
    assert result3.success is False
    # raw integer -> validation rejection
    assert result3.failure_stage == "validation"
    assert provider3.call_count == 0


# E8 — Governance bypass negative
def test_e8_governance_bypass_denied(tmp_path: Path):
    pipeline, store, gov, journal, _ = _governed_pipeline(tmp_path)
    action = _high_action("e8-idem")
    provider = AlwaysSuccessProvider()
    intent_id = _intent_for(action, "e8")
    result = pipeline.execute(action, provider=provider, intent_id=intent_id)

    assert result.success is False
    assert result.failure_stage == "approval"
    assert provider.call_count == 0
    records = journal.load()
    assert len(records) == 0

    pipeline2, store2, gov2, journal2, _ = _governed_pipeline(tmp_path / "scope", scope=("external://payments",))
    action2 = ExternalAction(provider="secrets", operation="charge", payload='{"password":"x"}', idempotency_key="e8-scope")
    grant2, _, _ = _grant_for_action(store2, action2, gov2, scope=("external://payments",), attempt=1)
    provider2 = AlwaysSuccessProvider()
    intent_id2 = _intent_for(action2, "e8-scope")
    result2 = pipeline2.execute(action2, provider=provider2, intent_id=intent_id2)
    assert result2.success is False
    assert result2.failure_stage == "validation"
    assert provider2.call_count == 0

    pipeline3, store3, gov3, journal3, _ = _governed_pipeline(tmp_path / "forged", scope=("external://",))
    action3 = _high_action("e8-forged")
    from simulation.agent.controller.controller_decision import ControllerDecision

    from simulation.agent.apply.external_executor import ExternalActionExecutor

    fake_decision = ControllerDecision(approved=False, reason="forged", patch_fingerprint="abc", approval_id="")
    executor = ExternalActionExecutor(approval_store=store3, governance=gov3, journal=journal3)
    synthetic3 = action3.to_patch_proposal(allowed_paths=("external://",))
    # Model B executor requires intent_id or attempt_context; give intent_id for scope check then auth denies
    intent_id3 = _intent_for(action3, "e8-forged")
    res = executor.execute(action3, fake_decision, synthetic3, scope=("external://",), provider=AlwaysSuccessProvider(), intent_id=intent_id3)
    assert res.outcome == ExternalOutcome.KNOWN_FAILURE
    assert "authorization denied" in res.reason.lower()


def test_spike_no_external_rollback_claim(tmp_path: Path):
    """Ensure external journal has no rollback types — external compensation not claimed."""
    journal = ExternalOutcomeJournal(str(tmp_path / "check.jsonl"))
    from simulation.agent.apply.external_outcome_journal import _VALID_NEXT

    all_types = set()
    for src, dsts in _VALID_NEXT.items():
        all_types.update(dsts)
        if src:
            all_types.add(src)
    assert "rolled_back" not in all_types
    assert "rollback_started" not in all_types
    assert "verified" not in all_types
    assert "external_timeout_unknown" in all_types
    assert "external_ambiguous_unknown" in all_types
