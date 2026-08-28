"""T-B3 — Stale CAS fail-closed (P10.3-C2b).

Proves:
- First open_attempt(A, expected=1) succeeds -> attempt 2
- Second stale open_attempt(A, expected=1) fails closed ValueError
- Zero durable mutation after stale failure
- HUMAN attempt 1 exactly 1, ATTEMPT_OPENED attempt 2 exactly 1, no attempt 3
"""

from pathlib import Path
import tempfile

from simulation.agent.apply.external_action import ExternalAction
from simulation.agent.apply.external_intent import create_intent
from simulation.agent.apply.external_outcome_journal import ExternalOutcomeJournal


def test_t_b3_stale_cas_fail_closed():
    tmp = Path(tempfile.mkdtemp())
    journal = ExternalOutcomeJournal(str(tmp / "ext.jsonl"))

    provider = "secrets"
    operation = "charge"
    payload = '{"password": "x"}'
    idempotency_key = "KEY_A"
    reason = "high"
    workspace = "ws1"
    request_nonce = "N1"

    intent_id = create_intent(provider, operation, payload, idempotency_key, reason, workspace, request_nonce)
    action = ExternalAction(provider=provider, operation=operation, payload=payload, idempotency_key=idempotency_key, reason=reason)

    # Attempt 1 -> TIMEOUT
    approval_1 = "approval_1"
    journal.record_intent(intent_id, action, attempt=1, approval_id=approval_1)
    journal.record_started(intent_id)
    journal.record_timeout_unknown(intent_id)

    # Verify latest attempt 1
    records = journal.load()
    latest = [r for r in records if r["intent_id"] == intent_id][-1]
    assert latest["record_type"] == "external_timeout_unknown"
    # Find latest attempt for intent
    latest_attempt = max(r.get("attempt", 0) for r in records if r["intent_id"] == intent_id and "attempt" in r)
    assert latest_attempt == 1

    # Caller 1: open_attempt expected 1 -> success, creates attempt 2
    approval_2 = "approval_2"
    context = journal.open_attempt(intent_id, expected_current_attempt=1, new_approval_id=approval_2)

    assert context.intent_id == intent_id
    assert context.attempt == 2
    assert context.expected_previous_attempt == 1
    assert context.approval_id == approval_2

    # After Caller 1, latest attempt 2
    records_after_1 = journal.load()
    latest_after_1 = max(r.get("attempt", 0) for r in records_after_1 if r["intent_id"] == intent_id and "attempt" in r)
    assert latest_after_1 == 2

    # Record counts before stale caller
    count_before = len(journal.load())
    human_before = sum(1 for r in journal.load() if r["intent_id"] == intent_id and r["record_type"] == "human_decision_required" and r.get("attempt") == 1)
    attempt_opened_before = sum(1 for r in journal.load() if r["intent_id"] == intent_id and r["record_type"] == "attempt_opened" and r.get("attempt") == 2)
    assert human_before == 1
    assert attempt_opened_before == 1

    # Caller 2: stale expected 1 -> must fail closed
    approval_stale = "approval_stale"
    try:
        journal.open_attempt(intent_id, expected_current_attempt=1, new_approval_id=approval_stale)
        assert False, "Expected ValueError for stale expected_current_attempt"
    except ValueError as e:
        assert "expected" in str(e).lower() or "latest" in str(e).lower() or "1" in str(e)

    # Zero mutation after stale failure
    count_after = len(journal.load())
    assert count_after == count_before, f"Stale call mutated journal: before {count_before} after {count_after}"

    human_after = sum(1 for r in journal.load() if r["intent_id"] == intent_id and r["record_type"] == "human_decision_required" and r.get("attempt") == 1)
    attempt_opened_after = sum(1 for r in journal.load() if r["intent_id"] == intent_id and r["record_type"] == "attempt_opened" and r.get("attempt") == 2)
    attempt_3 = sum(1 for r in journal.load() if r["intent_id"] == intent_id and r["record_type"] == "attempt_opened" and r.get("attempt") == 3)

    assert human_after == 1, f"HUMAN count should be 1, got {human_after}"
    assert attempt_opened_after == 1, f"ATTEMPT_OPENED 2 count should be 1, got {attempt_opened_after}"
    assert attempt_3 == 0, f"Attempt 3 should not exist, got {attempt_3}"

    # Final lineage: external_intent, started, timeout, human, attempt_opened
    final_records = [r for r in journal.load() if r["intent_id"] == intent_id]
    seq = [r["record_type"] for r in final_records]
    assert seq == ["external_intent", "external_started", "external_timeout_unknown", "human_decision_required", "attempt_opened"]
    # No duplicate transition
    assert seq.count("human_decision_required") == 1
    assert seq.count("attempt_opened") == 1
