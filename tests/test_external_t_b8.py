"""T-B8 — Interleaved Multi-Intent Retry Execution Independence (P10.3 MODEL B).

Proves the frozen invariant:
- A valid retry context belonging to Intent A must remain executable after
  another independent Intent B appends valid records to the same shared ExternalOutcomeJournal.
- Advancing the global journal tail via unrelated intents MUST NOT invalidate Intent A's Attempt 2 context.
- Intent A Attempt 2 should successfully pass start_opened_attempt() and complete to external_success.
- Both intents must coexist in the same durable journal with a valid hash chain.
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


def test_t_b8_control_single_intent_retry_succeeds():
    """Control case: single intent without interleaving starts retry and succeeds."""
    tmp = Path(tempfile.mkdtemp())
    journal = ExternalOutcomeJournal(str(tmp / "ext_ctrl.jsonl"))

    action = ExternalAction("prov", "op", "p", "K1", "r")
    intent_id = create_intent("prov", "op", "p", "K1", "r", "ws", "n1")

    journal.record_intent(intent_id, action, attempt=1, approval_id="appr1")
    journal.record_started(intent_id)
    journal.record_timeout_unknown(intent_id)

    ctx = journal.open_attempt(intent_id, expected_current_attempt=1, new_approval_id="appr2")
    assert ctx.attempt == 2

    journal.start_opened_attempt(ctx, action, approval_id="appr2")
    journal.record_success(intent_id)

    records = journal.load()
    seq = [r["record_type"] for r in records if r["intent_id"] == intent_id]
    assert seq == [
        TYPE_EXTERNAL_INTENT,
        TYPE_EXTERNAL_STARTED,
        TYPE_EXTERNAL_TIMEOUT_UNKNOWN,
        TYPE_HUMAN_DECISION_REQUIRED,
        TYPE_ATTEMPT_OPENED,
        TYPE_EXTERNAL_STARTED,
        TYPE_EXTERNAL_SUCCESS,
    ]
    assert records[-1]["record_type"] == TYPE_EXTERNAL_SUCCESS


def test_t_b8_interleaved_multi_intent_retry_independence():
    """Primary invariant test: Intent A retry must remain executable after Intent B advances global tail."""
    tmp = Path(tempfile.mkdtemp())
    journal_path = str(tmp / "ext_shared.jsonl")
    journal = ExternalOutcomeJournal(journal_path)

    # --------------------------------------------------
    # PHASE A — Create Intent A Attempt 1 and Open Attempt 2
    # --------------------------------------------------
    action_a = ExternalAction("provA", "opA", "payloadA", "KEY_A", "reasonA")
    intent_a = create_intent("provA", "opA", "payloadA", "KEY_A", "reasonA", "ws1", "nonceA")

    approval_a1 = "approval_A1"
    journal.record_intent(intent_a, action_a, attempt=1, approval_id=approval_a1)
    journal.record_started(intent_a)
    journal.record_timeout_unknown(intent_a)

    approval_a2 = "approval_A2"
    ctx_a = journal.open_attempt(
        intent_id=intent_a,
        expected_current_attempt=1,
        new_approval_id=approval_a2,
    )
    assert ctx_a.intent_id == intent_a
    assert ctx_a.attempt == 2
    assert ctx_a.expected_previous_attempt == 1
    assert ctx_a.approval_id == approval_a2

    # Verify ctx_a.previous_hash corresponds to Intent A's attempt_opened record
    records_after_open_a = journal.load()
    opened_record_a = [
        r for r in records_after_open_a
        if r["intent_id"] == intent_a and r["record_type"] == TYPE_ATTEMPT_OPENED
    ][-1]
    assert ctx_a.previous_hash == opened_record_a["current_hash"]
    a_attempt_opened_hash = ctx_a.previous_hash

    # --------------------------------------------------
    # PHASE B — Interleave Independent Intent B on Same Journal
    # --------------------------------------------------
    action_b = ExternalAction("provB", "opB", "payloadB", "KEY_B", "reasonB")
    intent_b = create_intent("provB", "opB", "payloadB", "KEY_B", "reasonB", "ws1", "nonceB")
    assert intent_a != intent_b

    approval_b1 = "approval_B1"
    journal.record_intent(intent_b, action_b, attempt=1, approval_id=approval_b1)
    journal.record_started(intent_b)
    journal.record_success(intent_b)

    # Verify Intent B is terminal success
    records_after_b = journal.load()
    assert records_after_b[-1]["intent_id"] == intent_b
    assert records_after_b[-1]["record_type"] == TYPE_EXTERNAL_SUCCESS

    # Explicitly establish that global journal tail has advanced away from Intent A's attempt_opened hash
    current_tail = journal.tail_hash()
    assert current_tail != a_attempt_opened_hash, (
        f"Expected tail hash {current_tail} to differ from Intent A attempt_opened hash {a_attempt_opened_hash}"
    )

    # --------------------------------------------------
    # PHASE C — Execute Intent A Attempt 2 via Production start_opened_attempt
    # --------------------------------------------------
    # The frozen invariant requires that Intent A's valid Attempt 2 context remains executable.
    journal.start_opened_attempt(
        context=ctx_a,
        action=action_a,
        approval_id=approval_a2,
    )
    journal.record_success(intent_a)

    # --------------------------------------------------
    # PHASE D — Verify Final Coexistence and Hash Chain
    # --------------------------------------------------
    final_records = journal.load()

    # Intent A per-intent sequence
    seq_a = [r["record_type"] for r in final_records if r["intent_id"] == intent_a]
    assert seq_a == [
        TYPE_EXTERNAL_INTENT,
        TYPE_EXTERNAL_STARTED,
        TYPE_EXTERNAL_TIMEOUT_UNKNOWN,
        TYPE_HUMAN_DECISION_REQUIRED,
        TYPE_ATTEMPT_OPENED,
        TYPE_EXTERNAL_STARTED,
        TYPE_EXTERNAL_SUCCESS,
    ]

    # Intent B per-intent sequence
    seq_b = [r["record_type"] for r in final_records if r["intent_id"] == intent_b]
    assert seq_b == [
        TYPE_EXTERNAL_INTENT,
        TYPE_EXTERNAL_STARTED,
        TYPE_EXTERNAL_SUCCESS,
    ]

    # Both intents reach terminal success
    assert journal._states.get(intent_a) == TYPE_EXTERNAL_SUCCESS
    assert journal._states.get(intent_b) == TYPE_EXTERNAL_SUCCESS

    # Full combined hash chain validates
    assert journal.load() is not None
