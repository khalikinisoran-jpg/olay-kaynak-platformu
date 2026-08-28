"""T-B1 — Stable intent_id lineage 1→2→3 (P10.3-C2b).

Frozen contract: intent_id stable via create_intent, record_intent(intent_id, action, attempt), open_attempt(intent_id, expected_current, new_approval_id)
"""

from pathlib import Path
import tempfile

from simulation.agent.apply.external_action import ExternalAction
from simulation.agent.apply.external_intent import create_intent
from simulation.agent.apply.external_outcome_journal import ExternalOutcomeJournal


def test_t_b1_stable_intent_lineage():
    tmp = Path(tempfile.mkdtemp())
    journal = ExternalOutcomeJournal(str(tmp / "ext.jsonl"))

    # Deterministic action
    provider = "secrets"
    operation = "charge"
    payload = '{"password": "x"}'
    idempotency_key = "KEY_A"
    reason = "high"
    workspace = "ws1"
    request_nonce = "N1"

    intent_id = create_intent(provider, operation, payload, idempotency_key, reason, workspace, request_nonce)
    # Pure deterministic: same inputs same intent_id
    intent_id2 = create_intent(provider, operation, payload, idempotency_key, reason, workspace, request_nonce)
    assert intent_id == intent_id2
    assert len(intent_id) == 16

    action = ExternalAction(provider=provider, operation=operation, payload=payload, idempotency_key=idempotency_key, reason=reason)

    # STEP 2 — attempt 1
    approval_1 = "approval_1"
    ret = journal.record_intent(intent_id, action, attempt=1, approval_id=approval_1)
    assert ret == intent_id
    journal.record_started(intent_id)
    journal.record_timeout_unknown(intent_id)

    records = journal.load()
    # Check latest state attempt 1 timeout
    last = [r for r in records if r["intent_id"] == intent_id][-1]
    assert last["record_type"] == "external_timeout_unknown"
    # attempt stored in intent record, not timeout
    assert any(r.get("attempt")==1 and r["record_type"]=="external_intent" for r in records)

    # Alternative check via intents grouping
    # Find latest attempt for intent_id
    attempts = [r.get("attempt") for r in records if r["intent_id"] == intent_id and "attempt" in r]
    assert 1 in attempts

    # STEP 3 — attempt 2 via open_attempt
    approval_2 = "approval_2"
    context_2 = journal.open_attempt(intent_id, expected_current_attempt=1, new_approval_id=approval_2)

    assert context_2.intent_id == intent_id
    assert context_2.attempt == 2
    assert context_2.approval_id == approval_2
    assert context_2.expected_previous_attempt == 1

    # Verify durable transition sequence after open_attempt
    records2 = journal.load()
    seq = [r["record_type"] for r in records2 if r["intent_id"] == intent_id]
    # Should be: intent, started, timeout, human, attempt_opened
    assert seq == ["external_intent", "external_started", "external_timeout_unknown", "human_decision_required", "attempt_opened"]

    journal.record_started(intent_id)
    journal.record_timeout_unknown(intent_id)
    records3 = journal.load()
    seq3 = [r["record_type"] for r in records3 if r["intent_id"] == intent_id]
    assert seq3 == ["external_intent", "external_started", "external_timeout_unknown", "human_decision_required", "attempt_opened", "external_started", "external_timeout_unknown"]
    # Check latest attempt 2
    last3 = [r for r in records3 if r["intent_id"]==intent_id][-1]
    assert last3["record_type"] == "external_timeout_unknown"

    # STEP 4 — attempt 3
    approval_3 = "approval_3"
    context_3 = journal.open_attempt(intent_id, expected_current_attempt=2, new_approval_id=approval_3)

    assert context_3.intent_id == intent_id
    assert context_3.attempt == 3
    assert context_3.approval_id == approval_3

    journal.record_started(intent_id)
    journal.record_success(intent_id)

    final_records = journal.load()
    seq_final = [r["record_type"] for r in final_records if r["intent_id"] == intent_id]
    assert seq_final == [
        "external_intent",
        "external_started",
        "external_timeout_unknown",
        "human_decision_required",
        "attempt_opened",
        "external_started",
        "external_timeout_unknown",
        "human_decision_required",
        "attempt_opened",
        "external_started",
        "external_success",
    ]

    # FINAL ASSERTS
    # attempt 1,2,3 same intent_id
    assert context_2.intent_id == intent_id
    assert context_3.intent_id == intent_id
    attempts_all = [r.get("attempt") for r in final_records if r["intent_id"]==intent_id and "attempt" in r]
    # Should contain 1,1? Check lineage exactly [1,2,3]
    # The journal stores attempt in intent, human, attempt_opened records
    # Filter distinct attempt values in order of appearance for intent records
    intent_attempts = []
    for r in final_records:
        if r["intent_id"] == intent_id and r["record_type"] in ("external_intent", "attempt_opened"):
            intent_attempts.append(r.get("attempt"))
    assert intent_attempts == [1, 2, 3]

    assert final_records[-1]["record_type"] == "external_success"
    # Latest attempt ==3
    latest_attempt = max(r.get("attempt", 0) for r in final_records if r["intent_id"]==intent_id and "attempt" in r)
    assert latest_attempt == 3

    # Same intent_id for all attempts
    for r in final_records:
        assert r["intent_id"] == intent_id
