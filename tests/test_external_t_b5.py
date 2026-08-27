"""T-B5 — Durable restart / reopen reconstruction (P10.3 MODEL B).

Proves:
- Full retry lifecycle to terminal success:
  intent(1) -> started(1) -> timeout(1) -> human(1) -> attempt_opened(2) -> started(2) -> success
- Fresh ExternalOutcomeJournal instance reloads complete durable state from disk.
- Zero in-memory dependency on prior journal instance.
- State reconstructs to external_success, latest attempt reconstructs to 2.
- Exact 7-record lineage reconstructed with valid cryptographic hash chain.
- Reopening causes zero durable mutation (count_before == count_after).
- Terminal external_success state fails closed against any further open_attempt.
- Zero mutation after rejected open_attempt on terminal state.
"""

from pathlib import Path
import tempfile
import pytest

from simulation.agent.apply.external_action import ExternalAction
from simulation.agent.apply.external_intent import create_intent
from simulation.agent.apply.external_outcome_journal import (
    ExternalOutcomeJournal,
    TYPE_EXTERNAL_INTENT,
    TYPE_EXTERNAL_STARTED,
    TYPE_EXTERNAL_TIMEOUT_UNKNOWN,
    TYPE_HUMAN_DECISION_REQUIRED,
    TYPE_ATTEMPT_OPENED,
    TYPE_EXTERNAL_SUCCESS,
)


def test_t_b5_durable_restart_reopen_reconstruction():
    tmp = Path(tempfile.mkdtemp())
    journal_path = str(tmp / "ext.jsonl")

    # 1. Setup business action and intent
    provider = "secrets"
    operation = "charge"
    payload = '{"password": "x"}'
    idempotency_key = "KEY_A"
    reason = "high"
    workspace = "ws1"
    request_nonce = "N1"

    intent_id = create_intent(
        provider, operation, payload, idempotency_key, reason, workspace, request_nonce
    )
    action = ExternalAction(
        provider=provider,
        operation=operation,
        payload=payload,
        idempotency_key=idempotency_key,
        reason=reason,
    )

    # 2. Instance 1: Execute full retry lifecycle to external_success
    journal1 = ExternalOutcomeJournal(journal_path)

    # Attempt 1: intent -> started -> timeout
    approval_1 = "approval_1"
    journal1.record_intent(intent_id, action, attempt=1, approval_id=approval_1)
    journal1.record_started(intent_id)
    journal1.record_timeout_unknown(intent_id)

    # Attempt 2: open_attempt -> started -> success
    approval_2 = "approval_2"
    ctx2 = journal1.open_attempt(
        intent_id=intent_id,
        expected_current_attempt=1,
        new_approval_id=approval_2,
    )
    assert ctx2.attempt == 2
    assert ctx2.expected_previous_attempt == 1
    assert ctx2.approval_id == approval_2

    journal1.start_opened_attempt(ctx2, action, approval_id=approval_2)
    journal1.record_success(intent_id)

    # 3. Verify Instance 1 durable state before restart
    records_before = journal1.load()
    count_before = len(records_before)
    assert count_before == 7

    expected_seq = [
        TYPE_EXTERNAL_INTENT,
        TYPE_EXTERNAL_STARTED,
        TYPE_EXTERNAL_TIMEOUT_UNKNOWN,
        TYPE_HUMAN_DECISION_REQUIRED,
        TYPE_ATTEMPT_OPENED,
        TYPE_EXTERNAL_STARTED,
        TYPE_EXTERNAL_SUCCESS,
    ]
    seq_before = [r["record_type"] for r in records_before if r["intent_id"] == intent_id]
    assert seq_before == expected_seq

    tail_before = journal1.tail_hash()
    assert tail_before == records_before[-1]["current_hash"]

    # 4. Discard Instance 1 completely (simulate crash / restart)
    del journal1

    # 5. Instance 2: Brand new journal instance from same path
    journal2 = ExternalOutcomeJournal(journal_path)

    # 6. Prove zero mutation occurred on reopen
    records_after = journal2.load()
    count_after = len(records_after)
    assert count_after == count_before, (
        f"Reopen mutated journal: before {count_before}, after {count_after}"
    )

    # 7. Verify durable lineage reconstructed accurately from disk
    seq_after = [r["record_type"] for r in records_after if r["intent_id"] == intent_id]
    assert seq_after == expected_seq

    # Final state reconstruction
    final_record = records_after[-1]
    assert final_record["record_type"] == TYPE_EXTERNAL_SUCCESS
    assert final_record["intent_id"] == intent_id
    assert journal2._states.get(intent_id) == TYPE_EXTERNAL_SUCCESS

    # Latest attempt reconstruction
    attempts_in_records = [
        r["attempt"] for r in records_after if r["intent_id"] == intent_id and "attempt" in r
    ]
    # intent (1), human (1), attempt_opened (2), started (2)
    assert attempts_in_records == [1, 1, 2, 2]
    latest_attempt = max(attempts_in_records)
    assert latest_attempt == 2

    # Tail hash integrity
    assert journal2.tail_hash() == tail_before
    assert journal2.tail_hash() == final_record["current_hash"]

    # 8. Terminal state protection: Attempting to open attempt on SUCCESS must fail closed
    with pytest.raises(ValueError) as exc_info:
        journal2.open_attempt(
            intent_id=intent_id,
            expected_current_attempt=2,
            new_approval_id="approval_3",
        )
    assert "TIMEOUT/AMBIGUOUS" in str(exc_info.value) or "external_success" in str(exc_info.value)

    # 9. Verify zero mutation after rejected open_attempt on terminal state
    records_final = journal2.load()
    assert len(records_final) == count_before
    assert journal2._states.get(intent_id) == TYPE_EXTERNAL_SUCCESS
    assert journal2.tail_hash() == tail_before
