"""T-B2 — New business = new intent_id (P10.3-C2a).

Proves:
- Same semantic inputs + same request_nonce => same intent_id (stable)
- Same semantic inputs + different request_nonce => different intent_id (new business)
- A and B are independent journal lineages, both attempt 1 → SUCCESS, B is not attempt 2 of A
"""

from pathlib import Path
import tempfile

from simulation.agent.apply.external_action import ExternalAction
from simulation.agent.apply.external_intent import create_intent
from simulation.agent.apply.external_outcome_journal import ExternalOutcomeJournal


def test_t_b2_new_business_new_intent():
    # Common semantic inputs
    provider = "secrets"
    operation = "charge"
    payload = '{"password": "x"}'
    idempotency_key = "KEY_A"
    reason = "high"
    workspace = "ws1"
    n1 = "N1"
    n2 = "N2"

    # A. Stable within same business: same N1 -> same A
    a1 = create_intent(provider, operation, payload, idempotency_key, reason, workspace, n1)
    a2 = create_intent(provider, operation, payload, idempotency_key, reason, workspace, n1)
    assert a1 == a2
    assert len(a1) == 16
    assert all(c in "0123456789abcdef" for c in a1)

    # B. New business gets new intent: same inputs but N2 != N1 -> B != A
    b = create_intent(provider, operation, payload, idempotency_key, reason, workspace, n2)
    assert b != a1
    assert len(b) == 16
    assert a1 != b

    # C. Independent journal lineages
    tmp = Path(tempfile.mkdtemp())
    journal = ExternalOutcomeJournal(str(tmp / "ext.jsonl"))

    action = ExternalAction(provider=provider, operation=operation, payload=payload, idempotency_key=idempotency_key, reason=reason)

    # A lineage: attempt 1 -> SUCCESS
    # Use A
    ret_a = journal.record_intent(a1, action, attempt=1, approval_id="approval_A")
    assert ret_a == a1
    journal.record_started(a1)
    journal.record_success(a1)

    # B lineage: attempt 1 -> SUCCESS (independent, not attempt 2 of A)
    ret_b = journal.record_intent(b, action, attempt=1, approval_id="approval_B")
    assert ret_b == b
    assert b != a1
    journal.record_started(b)
    journal.record_success(b)

    # Verify both lineages start at attempt 1
    records = journal.load()
    # Filter by intent
    rec_a = [r for r in records if r["intent_id"] == a1]
    rec_b = [r for r in records if r["intent_id"] == b]

    assert [r["record_type"] for r in rec_a] == ["external_intent", "external_started", "external_success"]
    assert [r["record_type"] for r in rec_b] == ["external_intent", "external_started", "external_success"]

    # Check attempt lineage
    assert rec_a[0].get("attempt") == 1
    assert rec_b[0].get("attempt") == 1

    # A records never attributed to B
    assert all(r["intent_id"] == a1 for r in rec_a)
    assert all(r["intent_id"] == b for r in rec_b)
    assert rec_a[0]["intent_id"] != rec_b[0]["intent_id"]

    # Terminal success of A does not prevent B
    # Already proven: B recorded successfully after A success
    # B is new intent, not attempt 2 of A
    # Ensure B is not attempt 2
    assert rec_b[0].get("attempt") == 1, "B must be attempt 1, not attempt 2 of A"

    # Explicit negative: changing only N1->N2 changes identity even though fingerprint same
    from simulation.agent.apply.external_action import ExternalAction as EA
    fp_a = EA(provider, operation, payload, idempotency_key, reason).fingerprint()
    fp_b = EA(provider, operation, payload, idempotency_key, reason).fingerprint()
    assert fp_a == fp_b  # same fingerprint
    assert a1 != b  # but intent_id differs due to N1 vs N2
