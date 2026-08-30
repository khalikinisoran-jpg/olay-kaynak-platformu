"""P10.12-B — approval lifecycle: duplicate-grant policy + revoke semantics.

Covers the P10.12-A decision package:
- duplicate-grant policy: at most ONE active grant per logical request
  (fingerprint + path + action + risk_level + attempt); duplicate active
  requests return the existing grant idempotently; consumed/expired/
  revoked grants do not block a legitimately new grant.
- revoke semantics: durable REVOKED ledger record; revoked grants can
  never be consumed or applied; revocation survives restart/rehydration;
  repeated revoke is idempotent; revoking consumed/applied grants is
  audit-only; expiry remains distinct from revocation.
- integrity: single-use and TTL behavior remain intact.
"""

import hashlib

import pytest

from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.approval.approval_ledger import ApprovalLedger


FP = hashlib.sha256(b"p10.12-b-approval-lifecycle").hexdigest()
PATH = "a.txt"
ACTION = "modify"
RISK = "HIGH"


def _store(tmp_path):
    return ApprovalStore(
        ledger=ApprovalLedger(path=str(tmp_path / "ledger.jsonl"))
    )


def _grant(store, fp=FP, path=PATH, risk=RISK, attempt=1, expires_at=None):
    return store.grant(
        patch_fingerprint=fp,
        path=path,
        action=ACTION,
        risk_level=risk,
        attempt=attempt,
        authorizer="tester",
        expires_at=expires_at,
    )


class _PatchStub:

    def __init__(self, fingerprint, path=PATH, action=ACTION):
        self._fingerprint = fingerprint
        self.path = path
        self.action = action

    def fingerprint(self):
        return self._fingerprint


def test_duplicate_active_request_returns_existing_grant(tmp_path):
    store = _store(tmp_path)
    g1 = _grant(store)
    g2 = _grant(store)
    assert g2.approval_id == g1.approval_id
    assert len(store) == 1


def test_duplicate_after_consume_mints_new_grant(tmp_path):
    store = _store(tmp_path)
    g1 = _grant(store)
    consumed = store.find_valid(FP, PATH, ACTION, RISK, 1)
    assert consumed.approval_id == g1.approval_id
    g2 = _grant(store)
    assert g2.approval_id != g1.approval_id
    again = store.find_valid(FP, PATH, ACTION, RISK, 1)
    assert again.approval_id == g2.approval_id


def test_duplicate_after_expiry_mints_new_grant(tmp_path):
    store = _store(tmp_path)
    _grant(store, expires_at=-60)
    g2 = _grant(store)
    found = store.find_valid(FP, PATH, ACTION, RISK, 1)
    assert found.approval_id == g2.approval_id


def test_duplicate_after_revoke_mints_new_grant(tmp_path):
    store = _store(tmp_path)
    g1 = _grant(store)
    assert store.revoke(g1.approval_id) is True
    g2 = _grant(store)
    assert g2.approval_id != g1.approval_id
    found = store.find_valid(FP, PATH, ACTION, RISK, 1)
    assert found.approval_id == g2.approval_id


def test_duplicate_policy_across_restart(tmp_path):
    store1 = _store(tmp_path)
    g1 = _grant(store1)
    store2 = _store(tmp_path)
    g2 = _grant(store2)
    assert g2.approval_id == g1.approval_id
    assert len(store2) == 1


def test_revoked_grant_cannot_be_consumed(tmp_path):
    store = _store(tmp_path)
    g1 = _grant(store)
    assert store.revoke(g1.approval_id) is True
    assert store.find_valid(FP, PATH, ACTION, RISK, 1) is None


def test_revoked_grant_cannot_authorize_apply(tmp_path):
    store = _store(tmp_path)
    g1 = _grant(store)
    patch = _PatchStub(FP)
    consumed = store.find_valid(FP, PATH, ACTION, RISK, 1, patch=patch)
    assert consumed.approval_id == g1.approval_id
    assert store.revoke(g1.approval_id) is True
    assert store.authorize_apply(g1.approval_id, patch) is False


def test_revocation_survives_restart(tmp_path):
    store1 = _store(tmp_path)
    g1 = _grant(store1)
    assert store1.revoke(g1.approval_id) is True
    store2 = _store(tmp_path)
    assert store2.find_valid(FP, PATH, ACTION, RISK, 1) is None
    assert store2.revoke(g1.approval_id) is False


def test_repeated_revoke_is_idempotent(tmp_path):
    store = _store(tmp_path)
    g1 = _grant(store)
    assert store.revoke(g1.approval_id) is True
    assert store.revoke(g1.approval_id) is False


def test_revoke_consumed_grant_is_audit_only(tmp_path):
    store = _store(tmp_path)
    g1 = _grant(store)
    patch = _PatchStub(FP)
    store.find_valid(FP, PATH, ACTION, RISK, 1, patch=patch)
    assert store.revoke(g1.approval_id) is True
    assert store.authorize_apply(g1.approval_id, patch) is False


def test_revoke_unknown_id_raises(tmp_path):
    store = _store(tmp_path)
    with pytest.raises(ValueError):
        store.revoke("unknown-approval-id")


def test_expiry_and_revocation_are_distinct(tmp_path):
    store = _store(tmp_path)
    g1 = _grant(store, expires_at=-60)
    assert store.revoke(g1.approval_id) is True
    assert store.find_valid(FP, PATH, ACTION, RISK, 1) is None


def test_single_use_behavior_unchanged(tmp_path):
    store = _store(tmp_path)
    g1 = _grant(store)
    patch = _PatchStub(FP)
    first = store.find_valid(FP, PATH, ACTION, RISK, 1, patch=patch)
    assert first.approval_id == g1.approval_id
    assert store.find_valid(FP, PATH, ACTION, RISK, 1) is None
    assert store.authorize_apply(g1.approval_id, patch) is True
    assert store.authorize_apply(g1.approval_id, patch) is False


def test_ttl_behavior_unchanged(tmp_path):
    store = _store(tmp_path)
    _grant(store, expires_at=-60)
    assert store.find_valid(FP, PATH, ACTION, RISK, 1) is None
    g2 = _grant(store, expires_at=3600)
    assert store.find_valid(FP, PATH, ACTION, RISK, 1) is not None


def test_cross_process_duplicate_suppression(tmp_path):
    store1 = _store(tmp_path)
    g1 = _grant(store1)
    store2 = _store(tmp_path)
    g2 = _grant(store2)
    assert g2.approval_id == g1.approval_id
    assert len(store2) == 1
