"""T-B6 — Bounded attempt exhaustion / Attempt 3 max cap (P10.3 MODEL B).

Proves:
- Model B permits attempts 1, 2, and 3 only.
- Attempt 1 (timeout) -> Attempt 2 (timeout) -> Attempt 3 (timeout) produces exact 11-record lineage.
- Attempting to open Attempt 4 (expected_current_attempt=3) fails closed with ValueError.
- Zero durable mutation on rejected Attempt 4 call (count_before == count_after == 11).
- No human_decision_required record appended for attempt 3 during rejected Attempt 4 call.
- No attempt_opened record with attempt == 4 exists.
- Latest durable attempt remains strictly 3.
- Full cryptographic hash chain remains valid via journal.load().
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
)


def test_t_b6_bounded_attempt_exhaustion_max_cap():
    tmp = Path(tempfile.mkdtemp())
    journal_path = str(tmp / "ext.jsonl")

    # 1. Business operation and stable intent_id
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

    journal = ExternalOutcomeJournal(journal_path)

    # 2. Attempt 1: intent -> started -> timeout_unknown
    approval_1 = "approval_1"
    journal.record_intent(intent_id, action, attempt=1, approval_id=approval_1)
    journal.record_started(intent_id)
    journal.record_timeout_unknown(intent_id)

    # 3. Attempt 2: open_attempt -> started -> timeout_unknown
    approval_2 = "approval_2"
    ctx2 = journal.open_attempt(
        intent_id=intent_id,
        expected_current_attempt=1,
        new_approval_id=approval_2,
    )
    assert ctx2.attempt == 2
    assert ctx2.expected_previous_attempt == 1
    assert ctx2.approval_id == approval_2

    journal.start_opened_attempt(ctx2, action, approval_id=approval_2)
    journal.record_timeout_unknown(intent_id)

    # 4. Attempt 3: open_attempt -> started -> timeout_unknown
    approval_3 = "approval_3"
    ctx3 = journal.open_attempt(
        intent_id=intent_id,
        expected_current_attempt=2,
        new_approval_id=approval_3,
    )
    assert ctx3.attempt == 3
    assert ctx3.expected_previous_attempt == 2
    assert ctx3.approval_id == approval_3

    journal.start_opened_attempt(ctx3, action, approval_id=approval_3)
    journal.record_timeout_unknown(intent_id)

    # 5. Verify durable lineage before Attempt 4 call
    records_before = journal.load()
    count_before = len(records_before)
    assert count_before == 11

    expected_lineage = [
        TYPE_EXTERNAL_INTENT,          # Attempt 1 intent (attempt=1)
        TYPE_EXTERNAL_STARTED,         # Attempt 1 started
        TYPE_EXTERNAL_TIMEOUT_UNKNOWN, # Attempt 1 timeout
        TYPE_HUMAN_DECISION_REQUIRED,  # Attempt 1 human (attempt=1)
        TYPE_ATTEMPT_OPENED,           # Attempt 2 opened (attempt=2)
        TYPE_EXTERNAL_STARTED,         # Attempt 2 started (attempt=2)
        TYPE_EXTERNAL_TIMEOUT_UNKNOWN, # Attempt 2 timeout
        TYPE_HUMAN_DECISION_REQUIRED,  # Attempt 2 human (attempt=2)
        TYPE_ATTEMPT_OPENED,           # Attempt 3 opened (attempt=3)
        TYPE_EXTERNAL_STARTED,         # Attempt 3 started (attempt=3)
        TYPE_EXTERNAL_TIMEOUT_UNKNOWN, # Attempt 3 timeout
    ]
    actual_seq_before = [r["record_type"] for r in records_before if r["intent_id"] == intent_id]
    assert actual_seq_before == expected_lineage

    # Verify attempt distribution: 1, 1, 2, 2, 2, 3, 3
    attempts_recorded = [
        r["attempt"] for r in records_before if r["intent_id"] == intent_id and "attempt" in r
    ]
    # external_intent(1), human(1), attempt_opened(2), started(2), human(2), attempt_opened(3), started(3)
    assert attempts_recorded == [1, 1, 2, 2, 2, 3, 3]

    latest_attempt_before = max(attempts_recorded)
    assert latest_attempt_before == 3

    tail_before = journal.tail_hash()
    assert tail_before == records_before[-1]["current_hash"]

    # 6. Attempt 4: open_attempt with expected_current_attempt=3 MUST fail closed
    approval_4 = "approval_4"
    with pytest.raises(ValueError) as exc_info:
        journal.open_attempt(
            intent_id=intent_id,
            expected_current_attempt=3,
            new_approval_id=approval_4,
        )

    # Must mention attempt cap (<3 or attempt limit)
    error_msg = str(exc_info.value)
    assert "<3" in error_msg or "3" in error_msg

    # 7. REQUIRED ASSERTIONS after rejected Attempt 4 call:
    records_after = journal.load()
    count_after = len(records_after)

    # Invariant: Zero durable mutation on rejected attempt-4 call
    assert count_after == count_before, (
        f"Attempt 4 rejection mutated journal: before {count_before}, after {count_after}"
    )

    # Invariant: No human_decision_required record appended for attempt 3
    human_attempt_3_count = sum(
        1 for r in records_after
        if r["intent_id"] == intent_id
        and r["record_type"] == TYPE_HUMAN_DECISION_REQUIRED
        and r.get("attempt") == 3
    )
    assert human_attempt_3_count == 0, (
        f"Unexpected human_decision_required for attempt 3: {human_attempt_3_count}"
    )

    # Invariant: No attempt_opened record for attempt 4
    attempt_4_count = sum(
        1 for r in records_after
        if r["intent_id"] == intent_id
        and r["record_type"] == TYPE_ATTEMPT_OPENED
        and r.get("attempt") == 4
    )
    assert attempt_4_count == 0, f"Unexpected attempt_opened for attempt 4: {attempt_4_count}"

    # Invariant: Latest durable attempt remains strictly 3
    attempts_after = [
        r["attempt"] for r in records_after if r["intent_id"] == intent_id and "attempt" in r
    ]
    latest_attempt_after = max(attempts_after)
    assert latest_attempt_after == 3

    # Invariant: Lineage matches exact 11 records
    actual_seq_after = [r["record_type"] for r in records_after if r["intent_id"] == intent_id]
    assert actual_seq_after == expected_lineage

    # Invariant: Hash chain remains completely valid and tail matches
    assert journal.tail_hash() == tail_before
    assert journal.tail_hash() == records_after[-1]["current_hash"]
