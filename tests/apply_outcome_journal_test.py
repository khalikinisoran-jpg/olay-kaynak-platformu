"""MISSION-019: apply-outcome journal tests.

Covers the journal state machine (INTENT -> APPLY_STARTED -> APPLIED ->
VERIFIED / ROLLED_BACK / APPLY_FAILED), fail-closed load on any
corruption, secret-safety of records, and integration with the
``ApplyExecutor`` / ``ApplyVerifyPipeline`` so a successful apply and a
rolled-back apply both leave a complete, restart-readable outcome.
"""

import json

import pytest

from simulation.agent.apply.apply_executor import ApplyExecutor
from simulation.agent.apply.apply_outcome_journal import (
    TYPE_APPLIED,
    TYPE_APPLY_FAILED,
    TYPE_APPLY_STARTED,
    TYPE_INTENT,
    TYPE_ROLLED_BACK,
    TYPE_ROLLBACK_STARTED,
    TYPE_VERIFIED,
    ApplyOutcomeJournal,
)
from simulation.agent.controller.controller_decision import (
    ControllerDecision
)
from simulation.agent.pipeline.apply_verify_pipeline import (
    ApplyVerifyPipeline
)
from simulation.agent.verify.verification_result import (
    FAIL,
    PASS,
    VerificationResult,
)
from simulation.agent.worker.patch_proposal import PatchProposal


def make_patch(tmp_path, name="notes.txt"):
    target = tmp_path / name
    target.write_text("value = 1\n", encoding="utf-8")
    return PatchProposal(
        path=str(target),
        action="modify",
        reason="Journal test.",
        old_content="value = 1\n",
        new_content="value = 2\n",
        allowed_paths=(str(target),),
    )


def approved_decision(patch, approval_id=""):
    return ControllerDecision(
        approved=True,
        reason="Journal test.",
        patch_fingerprint=patch.fingerprint(),
        approval_id=approval_id,
    )


class PassingVerification:

    def verify(self, paths, test_targets=()):
        return VerificationResult(
            status=PASS,
            exit_code=0,
            stdout="1 passed",
            stderr="",
            command=("python", "-m", "pytest", "-q"),
        )


class FailingVerification:

    def verify(self, paths, test_targets=()):
        return VerificationResult(
            status=FAIL,
            exit_code=1,
            stdout="",
            stderr="tests failed",
            command=("python", "-m", "pytest", "-q"),
        )


def record_types(journal):
    return [
        record["record_type"]
        for record in journal.load()
    ]


def test_full_success_lifecycle_is_durable(tmp_path):
    journal = ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )
    patch = make_patch(tmp_path)
    decision = approved_decision(patch)

    pipeline = ApplyVerifyPipeline(
        apply_executor=ApplyExecutor(journal=journal),
        verification_executor=PassingVerification(),
        journal=journal,
    )

    result = pipeline.execute(patch, decision, scope=(str(tmp_path),))

    assert result.success is True

    assert record_types(journal) == [
        TYPE_INTENT,
        TYPE_APPLY_STARTED,
        TYPE_APPLIED,
        TYPE_VERIFIED,
    ]

    reloaded = ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )

    assert record_types(reloaded) == [
        TYPE_INTENT,
        TYPE_APPLY_STARTED,
        TYPE_APPLIED,
        TYPE_VERIFIED,
    ]


def test_rollback_lifecycle_is_durable(tmp_path):
    journal = ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )
    patch = make_patch(tmp_path)
    decision = approved_decision(patch)

    pipeline = ApplyVerifyPipeline(
        apply_executor=ApplyExecutor(journal=journal),
        verification_executor=FailingVerification(),
        journal=journal,
    )

    result = pipeline.execute(patch, decision, scope=(str(tmp_path),))

    assert result.success is False
    assert result.rollback is not None
    assert result.rollback.success is True

    assert record_types(journal) == [
        TYPE_INTENT,
        TYPE_APPLY_STARTED,
        TYPE_APPLIED,
        TYPE_ROLLBACK_STARTED,
        TYPE_ROLLED_BACK,
    ]

    from pathlib import Path

    assert Path(patch.path).read_text(
        encoding="utf-8"
    ) == "value = 1\n"


def test_apply_denied_records_apply_failed(tmp_path):
    journal = ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )
    patch = make_patch(tmp_path)

    forged = ControllerDecision(
        approved=True,
        reason="forged",
        patch_fingerprint="wrong-fingerprint",
    )

    executor = ApplyExecutor(journal=journal)

    result = executor.apply(patch, forged, scope=(str(tmp_path),))

    assert result.success is False

    assert record_types(journal) == [
        TYPE_INTENT,
        TYPE_APPLY_FAILED,
    ]


def test_journal_records_do_not_contain_patch_content(tmp_path):
    journal = ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )
    patch = make_patch(tmp_path)

    executor = ApplyExecutor(journal=journal)

    decision = approved_decision(patch)

    result = executor.apply(patch, decision, scope=(str(tmp_path),))

    assert result.success is True

    text = journal.path.read_text(encoding="utf-8")

    assert "value = 1" not in text
    assert "value = 2" not in text

    records = journal.load()

    assert records[0]["patch_fingerprint"] == patch.fingerprint()

    for record in records:
        assert "old_content" not in record
        assert "new_content" not in record


def test_corrupted_json_fails_closed(tmp_path):
    journal = ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )
    patch = make_patch(tmp_path)
    executor = ApplyExecutor(journal=journal)
    executor.apply(patch, approved_decision(patch), scope=(str(tmp_path),))

    journal.path.write_text(
        "NOT JSON\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError):
        ApplyOutcomeJournal(
            path=tmp_path / "apply_journal.jsonl"
        ).load()


def test_tampered_hash_fails_closed(tmp_path):
    journal = ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )
    patch = make_patch(tmp_path)
    executor = ApplyExecutor(journal=journal)
    executor.apply(patch, approved_decision(patch), scope=(str(tmp_path),))

    records = [
        json.loads(line)
        for line in journal.path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    records[0]["path"] = "/attacker/path"

    journal.path.write_text(
        "\n".join(
            json.dumps(record)
            for record in records
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError):
        ApplyOutcomeJournal(
            path=tmp_path / "apply_journal.jsonl"
        ).load()


def test_out_of_order_transition_fails_closed(tmp_path):
    from simulation.security.hash_chain import HashChain

    journal = ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )

    intent_id = journal.record_intent(
        make_patch(tmp_path),
        attempt=1,
    )

    with pytest.raises(ValueError):
        journal.record_verified(intent_id)

    assert [
        record["record_type"]
        for record in journal.load()
    ] == [TYPE_INTENT]

    record = {
        "record_type": TYPE_APPLIED,
        "intent_id": intent_id,
        "reason": "",
        "previous_hash": journal.tail_hash(),
    }

    record["current_hash"] = HashChain.calculate(record)

    with open(
        journal.path,
        "a",
        encoding="utf-8",
    ) as f:
        f.write(json.dumps(record) + "\n")

    with pytest.raises(RuntimeError):
        journal.load()


def test_duplicate_intent_fails_closed(tmp_path):
    from simulation.security.hash_chain import HashChain

    journal = ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )

    patch = make_patch(tmp_path)

    intent_id = journal.record_intent(patch, attempt=1)

    record = {
        "record_type": TYPE_INTENT,
        "intent_id": intent_id,
        "patch_fingerprint": patch.fingerprint(),
        "path": patch.path,
        "action": patch.action,
        "attempt": 1,
        "approval_id": "",
        "old_content_hash": "",
        "new_content_hash": "",
        "reason": "",
        "previous_hash": journal.tail_hash(),
    }

    record["current_hash"] = HashChain.calculate(record)

    with open(
        journal.path,
        "a",
        encoding="utf-8",
    ) as f:
        f.write(json.dumps(record) + "\n")

    with pytest.raises(RuntimeError):
        journal.load()


def test_unknown_intent_fails_closed_on_load(tmp_path):
    from simulation.security.hash_chain import HashChain

    journal = ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )

    record = {
        "record_type": TYPE_APPLIED,
        "intent_id": "unknown-intent-id",
        "previous_hash": journal.tail_hash(),
    }

    record["current_hash"] = HashChain.calculate(record)

    with open(
        journal.path,
        "a",
        encoding="utf-8",
    ) as f:
        f.write(json.dumps(record) + "\n")

    with pytest.raises(RuntimeError):
        journal.load()


def test_chain_verifies_after_full_lifecycle(tmp_path):
    journal = ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )

    patch = make_patch(tmp_path)
    executor = ApplyExecutor(journal=journal)
    result = executor.apply(
        patch,
        approved_decision(patch),
        scope=(str(tmp_path),),
    )
    assert result.success is True

    journal.record_verified(result.intent_id)

    records = [
        json.loads(line)
        for line in journal.path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    previous = "GENESIS"

    for record in records:
        assert record["previous_hash"] == previous
        previous = record["current_hash"]

    assert previous != "GENESIS"


def test_rollback_failure_is_terminal_in_journal(tmp_path):
    journal = ApplyOutcomeJournal(
        path=tmp_path / "apply_journal.jsonl"
    )

    patch = make_patch(tmp_path)

    class NoRestoreExecutor(ApplyExecutor):

        def rollback(self, patch, scope=None):
            return False, "restore failed"

    pipeline = ApplyVerifyPipeline(
        apply_executor=NoRestoreExecutor(journal=journal),
        verification_executor=FailingVerification(),
        journal=journal,
    )

    result = pipeline.execute(
        patch,
        approved_decision(patch),
        scope=(str(tmp_path),),
    )

    assert result.rollback is not None
    assert result.rollback.success is False

    assert record_types(journal) == [
        TYPE_INTENT,
        TYPE_APPLY_STARTED,
        TYPE_APPLIED,
        TYPE_ROLLBACK_STARTED,
        "rollback_failed",
    ]
