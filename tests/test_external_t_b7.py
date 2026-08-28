"""T-B7 — Multi-Attempt Crash / Orphaned Lineage Detect-Only Reconciliation (P10.3 MODEL B).

Proves:
- External action crashing while Attempt 2 is in external_started state is recognized as orphaned.
- Fresh ExternalOutcomeJournal instance reloads raw un-adjudicated state from disk.
- ExternalReconciliationEngine.detect() is strictly detect-only:
  - report.total_intents == 1
  - report.orphaned_intents == (intent_id,)
  - report.ambiguous == 0
  - report.success == 0
  - report.failed == 0
  - report.anomalies == ()
- detect() causes zero external execution and zero durable journal mutation (delta == 0).
- Orphaned external_started state fails closed against open_attempt (cannot open Attempt 3).
- Rejected open_attempt causes zero mutation (no human record for attempt 2, no attempt_opened 3).
- Full cryptographic hash chain remains valid.
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
from simulation.agent.recovery.external_reconciliation import ExternalReconciliationEngine


def test_t_b7_multi_attempt_crash_orphaned_detect_only_reconciliation():
    tmp = Path(tempfile.mkdtemp())
    journal_path = str(tmp / "ext.jsonl")

    # 1. Setup business action and stable intent_id
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

    # 2. Instance 1: Construct Attempt 1 timeout -> Attempt 2 started (in-flight crash)
    journal1 = ExternalOutcomeJournal(journal_path)

    # Attempt 1: intent -> started -> timeout_unknown
    approval_1 = "approval_1"
    journal1.record_intent(intent_id, action, attempt=1, approval_id=approval_1)
    journal1.record_started(intent_id)
    journal1.record_timeout_unknown(intent_id)

    # Attempt 2: open_attempt -> started (simulating crash before terminal outcome)
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

    # Verify state before crash: exactly 6 records, final is external_started (attempt 2)
    expected_lineage = [
        TYPE_EXTERNAL_INTENT,          # Attempt 1 intent (attempt=1)
        TYPE_EXTERNAL_STARTED,         # Attempt 1 started
        TYPE_EXTERNAL_TIMEOUT_UNKNOWN, # Attempt 1 timeout
        TYPE_HUMAN_DECISION_REQUIRED,  # Attempt 1 human (attempt=1)
        TYPE_ATTEMPT_OPENED,           # Attempt 2 opened (attempt=2)
        TYPE_EXTERNAL_STARTED,         # Attempt 2 started (attempt=2)
    ]
    records_pre_crash = journal1.load()
    assert len(records_pre_crash) == 6
    assert [r["record_type"] for r in records_pre_crash if r["intent_id"] == intent_id] == expected_lineage
    assert records_pre_crash[-1]["record_type"] == TYPE_EXTERNAL_STARTED
    tail_pre_crash = journal1.tail_hash()

    # 3. Simulate process crash / loss of in-memory state
    del journal1

    # 4. Fresh journal object on restart from disk
    journal2 = ExternalOutcomeJournal(journal_path)
    records_fresh = journal2.load()
    assert len(records_fresh) == 6
    assert journal2._states.get(intent_id) == TYPE_EXTERNAL_STARTED
    assert journal2.tail_hash() == tail_pre_crash

    # 5. Detect-only reconciliation
    engine = ExternalReconciliationEngine(journal2)

    count_before_detect = len(journal2.load())
    tail_before_detect = journal2.tail_hash()

    report = engine.detect()

    # Exact reconciliation report assertions
    assert report.total_intents == 1
    assert report.orphaned_intents == (intent_id,)
    assert report.ambiguous == 0
    assert report.ambiguous_intents == ()
    assert report.success == 0
    assert report.failed == 0
    assert report.anomalies == ()

    # 6. Detect-only safety assertions: zero mutation, zero append
    count_after_detect = len(journal2.load())
    tail_after_detect = journal2.tail_hash()
    assert count_after_detect == count_before_detect == 6
    assert tail_after_detect == tail_before_detect

    # 7. Orphan fail-closed lockout: Attempting open_attempt on external_started must fail closed
    approval_3 = "approval_3"
    with pytest.raises(ValueError) as exc_info:
        journal2.open_attempt(
            intent_id=intent_id,
            expected_current_attempt=2,
            new_approval_id=approval_3,
        )
    error_msg = str(exc_info.value)
    assert "TIMEOUT/AMBIGUOUS" in error_msg or "external_started" in error_msg

    # Assert rejected open_attempt caused zero durable mutation
    records_after_rejection = journal2.load()
    assert len(records_after_rejection) == 6

    # Verify no human decision required was appended for attempt 2
    human_attempt_2_count = sum(
        1 for r in records_after_rejection
        if r["intent_id"] == intent_id
        and r["record_type"] == TYPE_HUMAN_DECISION_REQUIRED
        and r.get("attempt") == 2
    )
    assert human_attempt_2_count == 0

    # Verify no attempt_opened record was appended for attempt 3
    attempt_3_count = sum(
        1 for r in records_after_rejection
        if r["intent_id"] == intent_id
        and r["record_type"] == TYPE_ATTEMPT_OPENED
        and r.get("attempt") == 3
    )
    assert attempt_3_count == 0

    # 8. Durable lineage & hash chain assertions
    actual_seq_final = [r["record_type"] for r in records_after_rejection if r["intent_id"] == intent_id]
    assert actual_seq_final == expected_lineage

    # Exactly one external_intent
    intent_count = sum(1 for r in records_after_rejection if r["record_type"] == TYPE_EXTERNAL_INTENT)
    assert intent_count == 1

    # Exactly one attempt_opened (attempt=2)
    attempt_2_opened_count = sum(
        1 for r in records_after_rejection
        if r["record_type"] == TYPE_ATTEMPT_OPENED and r.get("attempt") == 2
    )
    assert attempt_2_opened_count == 1

    # Latest attempt remains 2
    attempts_recorded = [
        r["attempt"] for r in records_after_rejection if r["intent_id"] == intent_id and "attempt" in r
    ]
    assert attempts_recorded == [1, 1, 2, 2]
    assert max(attempts_recorded) == 2

    # Latest state remains external_started
    assert journal2._states.get(intent_id) == TYPE_EXTERNAL_STARTED

    # Hash chain validity
    assert journal2.tail_hash() == tail_pre_crash
    assert journal2.tail_hash() == records_after_rejection[-1]["current_hash"]
