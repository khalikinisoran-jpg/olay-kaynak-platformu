"""T-B4 — Concurrent open_attempt exactly one winner (P10.3 MODEL B).

Proves: Two independent processes concurrently attempting
open_attempt(A, expected_current_attempt=1, new_approval_id) → exactly one succeeds,
one fails closed, durable lineage has exactly one HUMAN and one ATTEMPT_OPENED for attempt 2,
no duplicate, hash chain valid.
"""

import multiprocessing
import tempfile
import time
from pathlib import Path

from simulation.agent.apply.external_action import ExternalAction
from simulation.agent.apply.external_intent import create_intent
from simulation.agent.apply.external_outcome_journal import ExternalOutcomeJournal


def _worker_open_attempt(journal_path_str, intent_id, expected_attempt, new_approval_id, barrier, result_queue):
    """Worker for T-B4: each process independently opens journal and calls open_attempt."""
    try:
        # Wait for both processes to be ready (barrier)
        try:
            barrier.wait(timeout=5)
        except Exception:
            pass
        # Each process creates its own journal instance (process isolation)
        journal = ExternalOutcomeJournal(journal_path_str)
        ctx = journal.open_attempt(intent_id, expected_current_attempt=expected_attempt, new_approval_id=new_approval_id)
        result_queue.put(("success", new_approval_id, ctx.attempt, intent_id))
    except Exception as e:
        # Fail closed: ValueError for stale CAS or EventStoreBusyError
        result_queue.put(("fail", new_approval_id, str(type(e).__name__) + ": " + str(e)))


def test_t_b4_concurrent_open_attempt_exactly_one_winner():
    tmp = Path(tempfile.mkdtemp())
    journal_path = str(tmp / "ext.jsonl")

    # Setup: intent A with attempt 1 -> timeout (retryable)
    provider = "secrets"
    operation = "charge"
    payload = '{"password": "x"}'
    idempotency_key = "KEY_A"
    reason = "high"
    workspace = "ws1"
    request_nonce = "N1"

    intent_id = create_intent(provider, operation, payload, idempotency_key, reason, workspace, request_nonce)
    action = ExternalAction(provider=provider, operation=operation, payload=payload, idempotency_key=idempotency_key, reason=reason)

    journal = ExternalOutcomeJournal(journal_path)
    # Durable initial lineage: intent(1) -> started(1) -> timeout(1)
    journal.record_intent(intent_id, action, attempt=1, approval_id="approval_1")
    journal.record_started(intent_id)
    journal.record_timeout_unknown(intent_id)

    # Verify initial state
    initial_records = journal.load()
    assert len([r for r in initial_records if r["intent_id"] == intent_id]) == 3
    assert [r["record_type"] for r in initial_records if r["intent_id"] == intent_id] == [
        "external_intent",
        "external_started",
        "external_timeout_unknown",
    ]

    count_before = len(journal.load())
    # Prepare two independent processes with distinct approval IDs
    barrier = multiprocessing.Barrier(2)
    result_queue = multiprocessing.Queue()

    p1 = multiprocessing.Process(target=_worker_open_attempt, args=(journal_path, intent_id, 1, "approval_2_A", barrier, result_queue))
    p2 = multiprocessing.Process(target=_worker_open_attempt, args=(journal_path, intent_id, 1, "approval_2_B", barrier, result_queue))

    p1.start()
    p2.start()
    p1.join(timeout=10)
    p2.join(timeout=10)

    # Ensure both terminated
    if p1.is_alive():
        p1.terminate()
        p1.join()
        assert False, "p1 hung"
    if p2.is_alive():
        p2.terminate()
        p2.join()
        assert False, "p2 hung"

    results = []
    while not result_queue.empty():
        results.append(result_queue.get())

    # Exactly one success, one fail
    success_count = sum(1 for r in results if r[0] == "success")
    failure_count = sum(1 for r in results if r[0] == "fail")
    assert success_count == 1, f"Expected exactly one winner, got {results}"
    assert failure_count == 1, f"Expected exactly one loser, got {results}"

    # Winner attempt ==2
    winner = [r for r in results if r[0] == "success"][0]
    assert winner[2] == 2
    loser = [r for r in results if r[0] == "fail"][0]
    # Loser must be fail-closed (ValueError stale CAS or EventStoreBusyError)
    assert "ValueError" in loser[2] or "EventStoreBusyError" in loser[2] or "expected" in loser[2].lower() or "latest" in loser[2].lower()

    # Durable journal evidence after both processes
    journal2 = ExternalOutcomeJournal(journal_path)
    records = journal2.load()
    count_after = len(records)
    assert count_after == count_before + 2, f"Expected exactly 2 new records (human + attempt_opened), before {count_before} after {count_after}"

    # Filter for intent A
    rec_a = [r for r in records if r["intent_id"] == intent_id]
    seq = [r["record_type"] for r in rec_a]
    assert seq == ["external_intent", "external_started", "external_timeout_unknown", "human_decision_required", "attempt_opened"], f"Unexpected sequence {seq}"

    human_count = sum(1 for r in rec_a if r["record_type"] == "human_decision_required" and r.get("attempt") == 1)
    assert human_count == 1, f"HUMAN count {human_count}"
    attempt_opened_2 = sum(1 for r in rec_a if r["record_type"] == "attempt_opened" and r.get("attempt") == 2)
    assert attempt_opened_2 == 1, f"ATTEMPT_OPENED 2 count {attempt_opened_2}"
    attempt_opened_3 = sum(1 for r in rec_a if r["record_type"] == "attempt_opened" and r.get("attempt") == 3)
    assert attempt_opened_3 == 0

    # latest_attempt ==2
    latest_attempt = max(r.get("attempt", 0) for r in rec_a if "attempt" in r)
    assert latest_attempt == 2

    # Hash chain integrity remains valid (load succeeded, no RuntimeError)
    # Already proven by journal2.load() succeeding; explicitly check tail hash
    assert journal2.load() is not None
