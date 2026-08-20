"""MISSION-019: startup reconciliation tests.

Proves that after a restart the system can *detect* orphaned apply
intents, orphaned mutations, consumed approvals without a terminal
outcome and duplicate-approval anomalies — without ever mutating a file
or bypassing the approval boundary. A corrupt journal fails closed.
"""

from pathlib import Path

import pytest

from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.apply.apply_outcome_journal import (
    TYPE_APPLIED,
    TYPE_APPLY_STARTED,
    TYPE_INTENT,
    TYPE_ROLLBACK_STARTED,
    ApplyOutcomeJournal,
)
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.controller.controller_decision import (
    ControllerDecision
)
from simulation.agent.recovery.startup_reconciliation import (
    CLASS_ORPHANED_APPLIED,
    CLASS_ORPHANED_ROLLBACK,
    CLASS_SUCCESS,
    CLASS_INTENT_ONLY,
    CLASS_ROLLED_BACK,
    ReconciliationEngine,
)
from simulation.agent.verify.verification_result import (
    FAIL,
    PASS,
    VerificationResult,
)
from simulation.agent.worker.patch_proposal import PatchProposal


def make_patch(tmp_path, name="target.txt"):
    target = tmp_path / name
    target.write_text("value = 1\n", encoding="utf-8")
    return PatchProposal(
        path=str(target),
        action="modify",
        reason="Reconciliation test.",
        old_content="value = 1\n",
        new_content="value = 2\n",
        allowed_paths=(str(target),),
    )


def make_journal(tmp_path):
    return ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )


def approved_decision(patch):
    return ControllerDecision(
        approved=True,
        reason="Reconciliation test.",
        patch_fingerprint=patch.fingerprint(),
    )


def test_reconciliation_empty_journal_is_clean(tmp_path):
    journal = make_journal(tmp_path)
    engine = ReconciliationEngine(
        journal=journal,
        allowed_paths=(str(tmp_path),),
    )
    report = engine.detect()
    assert report.intents == ()
    assert report.orphaned_mutations == ()
    assert report.anomalies == ()


def test_completed_success_is_terminal_not_orphaned(tmp_path):
    journal = make_journal(tmp_path)
    patch = make_patch(tmp_path)

    class PassingVerification:
        def verify(self, paths, test_targets=()):
            return VerificationResult(
                status=PASS,
                exit_code=0,
                stdout="ok",
                stderr="",
                command=("python", "-m", "pytest", "-q"),
            )

    from simulation.agent.pipeline.apply_verify_pipeline import (
        ApplyVerifyPipeline,
    )

    pipeline = ApplyVerifyPipeline(
        apply_executor=ApplyExecutor(journal=journal),
        verification_executor=PassingVerification(),
        journal=journal,
    )
    result = pipeline.execute(
        patch,
        approved_decision(patch),
        scope=(str(tmp_path),),
    )
    assert result.success is True

    report = ReconciliationEngine(
        journal=journal,
        allowed_paths=(str(tmp_path),),
    ).detect()

    assert len(report.intents) == 1
    assert report.intents[0].classification == CLASS_SUCCESS
    assert report.orphaned_mutations == ()


def test_orphaned_applied_mutation_is_detected(tmp_path):
    journal = make_journal(tmp_path)
    patch = make_patch(tmp_path)

    executor = ApplyExecutor(journal=journal)
    result = executor.apply(
        patch,
        approved_decision(patch),
        scope=(str(tmp_path),),
    )
    assert result.success is True

    assert Path(patch.path).read_text(
        encoding="utf-8"
    ) == "value = 2\n"

    report = ReconciliationEngine(
        journal=journal,
        allowed_paths=(str(tmp_path),),
    ).detect()

    assert len(report.orphaned_mutations) == 1
    orphan = report.orphaned_mutations[0]
    assert orphan.classification == CLASS_ORPHANED_APPLIED
    assert orphan.mutation_present is True
    assert orphan.rollback_pending is True


def test_orphan_after_rollback_start_is_detected(tmp_path):
    journal = make_journal(tmp_path)
    patch = make_patch(tmp_path)
    executor = ApplyExecutor(journal=journal)
    result = executor.apply(
        patch,
        approved_decision(patch),
        scope=(str(tmp_path),),
    )
    assert result.success is True
    journal.record_rollback_started(result.intent_id)

    report = ReconciliationEngine(
        journal=journal,
        allowed_paths=(str(tmp_path),),
    ).detect()

    assert len(report.orphaned_mutations) == 1
    assert report.orphaned_mutations[0].classification == (
        CLASS_ORPHANED_ROLLBACK
    )


def test_rolled_back_is_terminal(tmp_path):
    journal = make_journal(tmp_path)
    patch = make_patch(tmp_path)
    executor = ApplyExecutor(journal=journal)
    result = executor.apply(
        patch,
        approved_decision(patch),
        scope=(str(tmp_path),),
    )
    journal.record_rollback_started(result.intent_id)
    journal.record_rolled_back(result.intent_id)

    report = ReconciliationEngine(
        journal=journal,
        allowed_paths=(str(tmp_path),),
    ).detect()

    assert report.orphaned_mutations == ()
    assert report.intents[0].classification == CLASS_ROLLED_BACK
    assert report.intents[0].terminal is True


def test_intent_only_is_not_an_orphan(tmp_path):
    journal = make_journal(tmp_path)
    patch = make_patch(tmp_path)
    journal.record_intent(patch, attempt=1)

    report = ReconciliationEngine(
        journal=journal,
        allowed_paths=(str(tmp_path),),
    ).detect()

    assert report.orphaned_mutations == ()
    assert report.intents[0].classification == CLASS_INTENT_ONLY
    assert report.intents[0].mutation_present is False


def test_consumed_approval_without_outcome_is_flagged(tmp_path):
    journal = make_journal(tmp_path)
    patch = make_patch(tmp_path)

    store = ApprovalStore()
    approval = store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-test",
        expires_at=3600,
    )
    store.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        patch=patch,
    )

    intent_id = journal.record_intent(
        patch,
        attempt=1,
        approval_id=approval.approval_id,
    )
    journal.record_apply_started(intent_id)
    journal.record_applied(intent_id)

    report = ReconciliationEngine(
        journal=journal,
        allowed_paths=(str(tmp_path),),
        approval_store=store,
    ).detect()

    assert approval.approval_id in (
        report.consumed_approvals_without_outcome
    )


def test_duplicate_approval_across_intents_is_anomaly(tmp_path):
    journal = make_journal(tmp_path)

    first = make_patch(tmp_path, name="first.txt")
    second = make_patch(tmp_path, name="second.txt")

    first_id = journal.record_intent(
        first,
        attempt=1,
        approval_id="shared-approval",
    )
    journal.record_apply_started(first_id)
    journal.record_applied(first_id)

    second_id = journal.record_intent(
        second,
        attempt=1,
        approval_id="shared-approval",
    )
    journal.record_apply_started(second_id)
    journal.record_applied(second_id)

    report = ReconciliationEngine(
        journal=journal,
        allowed_paths=(str(tmp_path),),
    ).detect()

    assert any(
        "shared-approval" in anomaly
        for anomaly in report.anomalies
    )


def test_corrupt_journal_fails_closed(tmp_path):
    journal = make_journal(tmp_path)
    patch = make_patch(tmp_path)
    executor = ApplyExecutor(journal=journal)
    executor.apply(
        patch,
        approved_decision(patch),
        scope=(str(tmp_path),),
    )

    journal.path.write_text("NOT JSON\n", encoding="utf-8")

    with pytest.raises(RuntimeError):
        ReconciliationEngine(
            journal=journal,
            allowed_paths=(str(tmp_path),),
        ).detect()


def test_reconciliation_is_detect_only(tmp_path):
    journal = make_journal(tmp_path)
    patch = make_patch(tmp_path)
    executor = ApplyExecutor(journal=journal)
    result = executor.apply(
        patch,
        approved_decision(patch),
        scope=(str(tmp_path),),
    )
    assert result.success is True

    before = Path(patch.path).read_text(encoding="utf-8")

    report = ReconciliationEngine(
        journal=journal,
        allowed_paths=(str(tmp_path),),
    ).detect()

    assert len(report.orphaned_mutations) == 1

    after = Path(patch.path).read_text(encoding="utf-8")

    assert after == before
