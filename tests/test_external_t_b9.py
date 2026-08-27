"""T-B9 — Interleaved Multi-Intent Crash / Restart Reconciliation Independence (P10.3 MODEL B).

Proves the frozen invariant:
- Independent intents A and B coexisting and interleaved in a shared journal.
- Intent A opens Attempt 2 (human_decision_required, attempt_opened).
- Intent B executes completely (intent, started, success) on the same shared journal,
  advancing the global tail hash.
- Intent A starts Attempt 2 (external_started) despite the intervening Intent B records.
- Process crashes before any terminal record for Intent A Attempt 2.
- Fresh ExternalOutcomeJournal instance reloads both lineages from disk:
  - Intent A: external_started (attempt=2)
  - Intent B: external_success (attempt=1)
- ExternalReconciliationEngine.detect() reports:
  - total_intents == 2
  - orphaned_intents == (intent_A,)
  - ambiguous == 0
  - success == 1
  - failed == 0
  - anomalies == ()
- detect() causes zero durable mutations and no state drift.
- Fail-closed protections:
  - Intent A in-flight orphaned state cannot open Attempt 3.
  - Intent B terminal success cannot open Attempt 2.
- Full interleaved cryptographic hash chain validates from GENESIS.
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
from simulation.agent.recovery.external_reconciliation import ExternalReconciliationEngine


def test_t_b9_interleaved_multi_intent_crash_restart_reconciliation_independence():
    tmp = Path(tempfile.mkdtemp())
    journal_path = str(tmp / "ext_shared.jsonl")

    # 1. Setup two independent business intents
    action_a = ExternalAction("provA", "opA", "payloadA", "KEY_A", "reasonA")
    intent_a = create_intent("provA", "opA", "payloadA", "KEY_A", "reasonA", "ws1", "nonceA")

    action_b = ExternalAction("provB", "opB", "payloadB", "KEY_B", "reasonB")
    intent_b = create_intent("provB", "opB", "payloadB", "KEY_B", "reasonB", "ws1", "nonceB")
    assert intent_a != intent_b

    journal1 = ExternalOutcomeJournal(journal_path)

    # --------------------------------------------------
    # PHASE A — Intent A: Attempt 1 Timeout -> Open Attempt 2
    # --------------------------------------------------
    approval_a1 = "approval_A1"
    journal1.record_intent(intent_a, action_a, attempt=1, approval_id=approval_a1)
    journal1.record_started(intent_a)
    journal1.record_timeout_unknown(intent_a)

    approval_a2 = "approval_A2"
    ctx_a = journal1.open_attempt(
        intent_id=intent_a,
        expected_current_attempt=1,
        new_approval_id=approval_a2,
    )
    assert ctx_a.intent_id == intent_a
    assert ctx_a.attempt == 2
    assert ctx_a.expected_previous_attempt == 1
    assert ctx_a.approval_id == approval_a2

    records_after_open_a = journal1.load()
    opened_rec_a = [
        r for r in records_after_open_a
        if r["intent_id"] == intent_a and r["record_type"] == TYPE_ATTEMPT_OPENED
    ][-1]
    a_attempt_opened_hash = ctx_a.previous_hash
    assert a_attempt_opened_hash == opened_rec_a["current_hash"]

    # --------------------------------------------------
    # PHASE B — Interleave Independent Intent B on SAME Journal
    # --------------------------------------------------
    approval_b1 = "approval_B1"
    journal1.record_intent(intent_b, action_b, attempt=1, approval_id=approval_b1)
    journal1.record_started(intent_b)
    journal1.record_success(intent_b)

    # Assert Intent B completed to success
    records_after_b = journal1.load()
    assert records_after_b[-1]["intent_id"] == intent_b
    assert records_after_b[-1]["record_type"] == TYPE_EXTERNAL_SUCCESS

    # Prove global tail hash has advanced away from Intent A's attempt_opened hash
    tail_after_b = journal1.tail_hash()
    assert tail_after_b != a_attempt_opened_hash

    # --------------------------------------------------
    # PHASE C — Start Intent A Attempt 2 (In-Flight Crash State)
    # --------------------------------------------------
    journal1.start_opened_attempt(
        context=ctx_a,
        action=action_a,
        approval_id=approval_a2,
    )

    # Verify physical records immediately before simulated crash
    records_pre_crash = journal1.load()
    assert len(records_pre_crash) == 9
    assert records_pre_crash[-1]["intent_id"] == intent_a
    assert records_pre_crash[-1]["record_type"] == TYPE_EXTERNAL_STARTED
    assert records_pre_crash[-1]["attempt"] == 2
    tail_pre_crash = journal1.tail_hash()

    # --------------------------------------------------
    # PHASE D — Crash / Restart Simulation
    # --------------------------------------------------
    del journal1

    journal2 = ExternalOutcomeJournal(journal_path)
    records_fresh = journal2.load()
    assert len(records_fresh) == 9
    assert journal2.tail_hash() == tail_pre_crash

    # Verify reconstructed states & latest attempts
    assert journal2._states.get(intent_a) == TYPE_EXTERNAL_STARTED
    assert journal2._states.get(intent_b) == TYPE_EXTERNAL_SUCCESS

    attempts_a = [
        r["attempt"] for r in records_fresh if r["intent_id"] == intent_a and "attempt" in r
    ]
    assert attempts_a == [1, 1, 2, 2]
    assert max(attempts_a) == 2

    attempts_b = [
        r["attempt"] for r in records_fresh if r["intent_id"] == intent_b and "attempt" in r
    ]
    assert attempts_b == [1]
    assert max(attempts_b) == 1

    # --------------------------------------------------
    # PHASE E — Detect-Only Reconciliation
    # --------------------------------------------------
    engine = ExternalReconciliationEngine(journal2)

    count_before_detect = len(journal2.load())
    tail_before_detect = journal2.tail_hash()
    state_a_before_detect = journal2._states.get(intent_a)
    state_b_before_detect = journal2._states.get(intent_b)

    report = engine.detect()

    # Assert exact report contents
    assert report.total_intents == 2
    assert report.orphaned_intents == (intent_a,)
    assert intent_b not in report.orphaned_intents
    assert report.ambiguous == 0
    assert report.ambiguous_intents == ()
    assert report.success == 1
    assert report.failed == 0
    assert report.anomalies == ()

    # Detect-only safety assertions: zero mutation, zero append, state intact
    count_after_detect = len(journal2.load())
    tail_after_detect = journal2.tail_hash()
    assert count_after_detect == count_before_detect == 9
    assert tail_after_detect == tail_before_detect
    assert journal2._states.get(intent_a) == state_a_before_detect == TYPE_EXTERNAL_STARTED
    assert journal2._states.get(intent_b) == state_b_before_detect == TYPE_EXTERNAL_SUCCESS

    # --------------------------------------------------
    # PHASE F — Fail-Closed Assertions Post-Reconciliation
    # --------------------------------------------------
    # Intent A in-flight orphaned state cannot open Attempt 3
    with pytest.raises(ValueError) as exc_a:
        journal2.open_attempt(
            intent_id=intent_a,
            expected_current_attempt=2,
            new_approval_id="approval_A3",
        )
    assert "TIMEOUT/AMBIGUOUS" in str(exc_a.value) or "external_started" in str(exc_a.value)
    assert len(journal2.load()) == 9

    # Intent B terminal success cannot open retry
    with pytest.raises(ValueError) as exc_b:
        journal2.open_attempt(
            intent_id=intent_b,
            expected_current_attempt=1,
            new_approval_id="approval_B2",
        )
    assert "TIMEOUT/AMBIGUOUS" in str(exc_b.value) or "external_success" in str(exc_b.value)
    assert len(journal2.load()) == 9

    # --------------------------------------------------
    # PHASE G — Durable Lineage & Physical Interleaving Verification
    # --------------------------------------------------
    final_records = journal2.load()

    # Logical sequence Intent A
    seq_a = [r["record_type"] for r in final_records if r["intent_id"] == intent_a]
    assert seq_a == [
        TYPE_EXTERNAL_INTENT,
        TYPE_EXTERNAL_STARTED,
        TYPE_EXTERNAL_TIMEOUT_UNKNOWN,
        TYPE_HUMAN_DECISION_REQUIRED,
        TYPE_ATTEMPT_OPENED,
        TYPE_EXTERNAL_STARTED,
    ]

    # Logical sequence Intent B
    seq_b = [r["record_type"] for r in final_records if r["intent_id"] == intent_b]
    assert seq_b == [
        TYPE_EXTERNAL_INTENT,
        TYPE_EXTERNAL_STARTED,
        TYPE_EXTERNAL_SUCCESS,
    ]

    # Physical interleaved sequence check
    physical_pairs = [(r["intent_id"], r["record_type"]) for r in final_records]
    assert physical_pairs == [
        (intent_a, TYPE_EXTERNAL_INTENT),
        (intent_a, TYPE_EXTERNAL_STARTED),
        (intent_a, TYPE_EXTERNAL_TIMEOUT_UNKNOWN),
        (intent_a, TYPE_HUMAN_DECISION_REQUIRED),
        (intent_a, TYPE_ATTEMPT_OPENED),
        (intent_b, TYPE_EXTERNAL_INTENT),
        (intent_b, TYPE_EXTERNAL_STARTED),
        (intent_b, TYPE_EXTERNAL_SUCCESS),
        (intent_a, TYPE_EXTERNAL_STARTED),
    ]

    # Exactly 2 external_intent records total
    assert sum(1 for r in final_records if r["record_type"] == TYPE_EXTERNAL_INTENT) == 2

    # Exactly 1 attempt_opened for Attempt 2, 0 for Attempt 3
    assert sum(1 for r in final_records if r["record_type"] == TYPE_ATTEMPT_OPENED and r.get("attempt") == 2) == 1
    assert sum(1 for r in final_records if r["record_type"] == TYPE_ATTEMPT_OPENED and r.get("attempt") == 3) == 0

    # Full cryptographic hash chain validates
    assert journal2.tail_hash() == tail_pre_crash
    assert journal2.tail_hash() == final_records[-1]["current_hash"]
