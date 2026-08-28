"""P10.3-B — Approval binding integrity for idempotency_key (focused tests T1–T6) migrated to Model B."""

from pathlib import Path

import pytest

from simulation.agent.approval.approval_ledger import ApprovalLedger
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.apply.external_action import ExternalAction
from simulation.agent.apply.external_intent import create_intent
from simulation.agent.apply.external_outcome_journal import ExternalOutcomeJournal
from simulation.agent.apply.external_provider import AlwaysSuccessProvider, ExternalOutcome
from simulation.agent.pipeline.external_action_pipeline import ExternalActionPipeline
from simulation.agent.apply.external_executor import ExternalActionExecutor
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
    return pipeline, store, gov, journal


def _high_action(provider="secrets", operation="charge", payload='{"password":"x"}', idempotency_key="KEY_A", reason="high"):
    return ExternalAction(provider=provider, operation=operation, payload=payload, idempotency_key=idempotency_key, reason=reason)


def _intent_for(action: ExternalAction, nonce: str):
    return create_intent(action.provider, action.operation, action.payload, action.idempotency_key, action.reason, "binding", nonce)


# T1 — Different idempotency_key denied
def test_t1_different_idempotency_key_denied(tmp_path: Path):
    pipeline, store, gov, journal = _pipeline(tmp_path)
    action_a = _high_action(idempotency_key="KEY_A")
    action_b = _high_action(idempotency_key="KEY_B")

    syn_a = action_a.to_patch_proposal(allowed_paths=("external://",))
    syn_b = action_b.to_patch_proposal(allowed_paths=("external://",))
    assert syn_a.fingerprint() != syn_b.fingerprint(), "Synthetic fingerprint must include idempotency_key"
    assert action_a.fingerprint() != action_b.fingerprint()

    decision_a = gov.evaluate(syn_a)
    assert decision_a.requires_human_approval is True
    store.grant(
        patch_fingerprint=syn_a.fingerprint(),
        path=syn_a.path,
        action=syn_a.action,
        risk_level=decision_a.risk_level.value,
        attempt=1,
        authorizer="tester",
        expires_at=3600,
    )

    provider_b = AlwaysSuccessProvider()
    intent_b = _intent_for(action_b, "t1-b")
    result_b = pipeline.execute(action_b, provider=provider_b, intent_id=intent_b)

    assert result_b.success is False
    assert result_b.failure_stage == "approval"
    assert provider_b.call_count == 0
    assert len(journal.load()) == 0
    assert decision_a.risk_level.value == "HIGH"


# T2 — Same idempotency_key preserves normal flow
def test_t2_same_key_preserves_flow(tmp_path: Path):
    pipeline, store, gov, journal = _pipeline(tmp_path)
    action = _high_action(idempotency_key="same-key")
    syn = action.to_patch_proposal(allowed_paths=("external://",))
    decision = gov.evaluate(syn)
    store.grant(
        patch_fingerprint=syn.fingerprint(),
        path=syn.path,
        action=syn.action,
        risk_level=decision.risk_level.value,
        attempt=1,
        authorizer="tester",
        expires_at=3600,
    )
    provider = AlwaysSuccessProvider()
    intent_id = _intent_for(action, "t2")
    result = pipeline.execute(action, provider=provider, intent_id=intent_id)

    assert result.success is True
    assert result.external_result.outcome == ExternalOutcome.KNOWN_SUCCESS
    assert provider.call_count == 1
    records = journal.load()
    assert [r["record_type"] for r in records] == ["external_intent", "external_started", "external_success"]


# T3 — Single-use still holds
def test_t3_single_use_after_success(tmp_path: Path):
    pipeline, store, gov, journal = _pipeline(tmp_path)
    action = _high_action(idempotency_key="t3-key")
    syn = action.to_patch_proposal(allowed_paths=("external://",))
    decision = gov.evaluate(syn)
    store.grant(
        patch_fingerprint=syn.fingerprint(),
        path=syn.path,
        action=syn.action,
        risk_level=decision.risk_level.value,
        attempt=1,
        authorizer="tester",
        expires_at=3600,
    )
    provider1 = AlwaysSuccessProvider()
    intent_id = _intent_for(action, "t3")
    r1 = pipeline.execute(action, provider=provider1, intent_id=intent_id)
    assert r1.success is True
    assert provider1.call_count == 1

    provider2 = AlwaysSuccessProvider()
    # Reuse same intent_id -> approval already consumed -> approval denial
    r2 = pipeline.execute(action, provider=provider2, intent_id=intent_id)
    assert r2.success is False
    assert r2.failure_stage == "approval"
    assert provider2.call_count == 0


# T4 — Attempt binding still holds (raw integer rejected, proper retry requires context)
def test_t4_attempt_binding(tmp_path: Path):
    pipeline, store, gov, _ = _pipeline(tmp_path)
    action = _high_action(idempotency_key="t4-key")
    syn = action.to_patch_proposal(allowed_paths=("external://",))
    decision = gov.evaluate(syn)
    store.grant(
        patch_fingerprint=syn.fingerprint(),
        path=syn.path,
        action=syn.action,
        risk_level=decision.risk_level.value,
        attempt=1,
        authorizer="tester",
        expires_at=3600,
    )
    # Raw attempt integer is not valid retry authority — must be rejected at validation
    provider = AlwaysSuccessProvider()
    result = pipeline.execute(action, provider=provider, attempt=2)
    assert result.success is False
    # raw integer -> validation fail-closed
    assert result.failure_stage == "validation"
    assert provider.call_count == 0


# T5 — Worker pipeline regression (file patch still governed)
def test_t5_worker_pipeline_unchanged(tmp_path: Path):
    from simulation.agent.approval.approval_validation import is_approval_valid
    from simulation.agent.worker.patch_proposal import PatchProposal

    patch = PatchProposal(
        path="allowed/file.py",
        action="modify",
        old_content="hello",
        new_content="hello fixed",
        reason="test",
        allowed_paths=("allowed",),
    )
    ledger = ApprovalLedger(str(tmp_path / "ledger2.jsonl"))
    store = ApprovalStore(ledger=ledger)
    gov = GovernanceEvaluator(risk_engine=RiskEngine(), risk_policy=RiskPolicy())
    decision = gov.evaluate(patch)
    patch_high = PatchProposal(
        path="secrets/creds.py",
        action="modify",
        old_content="x",
        new_content='{"password":"x"}',
        reason="high",
        allowed_paths=("secrets",),
    )
    decision_high = gov.evaluate(patch_high)
    assert decision_high.requires_human_approval is True
    approval = store.grant(
        patch_fingerprint=patch_high.fingerprint(),
        path=patch_high.path,
        action=patch_high.action,
        risk_level=decision_high.risk_level.value,
        attempt=1,
        authorizer="tester",
        expires_at=3600,
    )
    found = store.find_valid(
        patch_high.fingerprint(),
        path=patch_high.path,
        action=patch_high.action,
        risk_level=decision_high.risk_level.value,
        attempt=1,
        patch=patch_high,
    )
    assert found is not None
    valid, _ = is_approval_valid(found, patch_high, decision_high.risk_level.value, 1)
    assert valid is True
    fake_patch = PatchProposal(
        path="secrets/creds.py",
        action="modify",
        old_content="x",
        new_content='{"password":"y"}',
        reason="high",
        allowed_paths=("secrets",),
    )
    valid2, reason = is_approval_valid(found, fake_patch, decision_high.risk_level.value, 1)
    assert valid2 is False
    assert "fingerprint" in reason


# T6 — Shared validator proof
def test_t6_shared_validator_proof(tmp_path: Path):
    from simulation.agent.approval import approval_validation
    from simulation.agent.pipeline import worker_action_pipeline as wap_mod
    from simulation.agent.pipeline import external_action_pipeline as eap_mod

    assert hasattr(wap_mod, "is_approval_valid"), "WorkerActionPipeline should import shared validator"
    assert hasattr(eap_mod, "is_approval_valid"), "ExternalActionPipeline should import shared validator"
    assert wap_mod.is_approval_valid is approval_validation.is_approval_valid
    assert eap_mod.is_approval_valid is approval_validation.is_approval_valid

    import inspect

    src_w = inspect.getsource(wap_mod.WorkerActionPipeline._approval_is_valid)
    src_e = inspect.getsource(eap_mod.ExternalActionPipeline._approval_is_valid)
    assert "is_approval_valid" in src_w, "Worker pipeline should delegate to shared"
    assert "is_approval_valid" in src_e, "External pipeline should delegate to shared"

    original = approval_validation.is_approval_valid

    def always_deny(*args, **kwargs):
        return False, "injected deny"

    wap_mod.is_approval_valid = always_deny
    eap_mod.is_approval_valid = always_deny
    approval_validation.is_approval_valid = always_deny

    try:
        from simulation.agent.worker.patch_proposal import PatchProposal

        patch = PatchProposal(
            path="secrets/creds.py",
            action="modify",
            old_content="x",
            new_content='{"password":"x"}',
            reason="high",
            allowed_paths=("secrets",),
        )
        ledger = ApprovalLedger(str(tmp_path / "ledger_t6.jsonl"))
        store = ApprovalStore(ledger=ledger)
        gov = GovernanceEvaluator(risk_engine=RiskEngine(), risk_policy=RiskPolicy())
        decision = gov.evaluate(patch)
        store.grant(
            patch_fingerprint=patch.fingerprint(),
            path=patch.path,
            action=patch.action,
            risk_level=decision.risk_level.value,
            attempt=1,
            authorizer="tester",
            expires_at=3600,
        )
        found = store.find_valid(
            patch.fingerprint(),
            path=patch.path,
            action=patch.action,
            risk_level=decision.risk_level.value,
            attempt=1,
            patch=patch,
        )
        from simulation.agent.approval.approval_validation import is_approval_valid as shared_check

        valid_w, _ = wap_mod.WorkerActionPipeline._approval_is_valid(found, patch, decision.risk_level.value, 1)
        valid_e, _ = eap_mod.ExternalActionPipeline._approval_is_valid(found, patch, decision.risk_level.value, 1)
        assert valid_w is False
        assert valid_e is False
    finally:
        wap_mod.is_approval_valid = original
        eap_mod.is_approval_valid = original
        approval_validation.is_approval_valid = original
