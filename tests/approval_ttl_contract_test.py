"""Q1 APPROVAL TTL CONTRACT — the advertised 3600s TTL bound at grant time.

G1: NEW test module; no existing test module is modified.

Product contract (pre-existing, advertised in CLI/UI output):
approvals expire 3600 seconds after granting; expired approvals are
rejected at execution. These tests bind that contract:

A) grant via agent_adapter.approve persists a non-empty expires_at
   exactly TTL seconds in the future
B) approval is valid before expiration
C) expired approval is rejected (find_valid -> None; shared
   validation reports expiry)
D) persisted expired approval remains expired after ledger reload
E) fingerprint binding remains intact
F) single-use consumption remains intact

No real waiting: expiry strings are constructed with the existing
iso_in_future / iso_in_past helpers (second-granularity ISO-8601 UTC,
lexicographically comparable by Approval.is_expired).
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from simulation.agent.approval.approval import (
    Approval,
    iso_in_future,
    iso_in_past,
)
from simulation.agent.approval.approval_ledger import ApprovalLedger
from simulation.agent.approval.approval_store import ApprovalStore
from simulation.agent.approval.approval_validation import is_approval_valid
from simulation.agent.worker.patch_proposal import PatchProposal

from tanuq import agent_adapter
from tanuq.config import APPROVAL_TTL_SECONDS, tanuq_dir
from tanuq.runtime import load_environment


FP = "f" * 64
OTHER_FP = "a" * 64


def _patch(path="demo.txt", fingerprint=FP):
    """A stand-in patch object exposing the fields the store binds to."""
    return type(
        "Patch",
        (),
        {
            "path": path,
            "action": "modify",
            "fingerprint": lambda self: fingerprint,
        },
    )()


@pytest.fixture
def env(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "demo.txt").write_text("hello", encoding="utf-8", newline="")
    monkeypatch.chdir(ws)
    from tanuq.config import init_workspace

    init_workspace(ws)
    return load_environment(ws)


# --- A) agent_adapter.approve binds the advertised TTL -------------------


def test_approve_persists_expires_at_exactly_ttl_seconds_ahead(env):
    payload = json.dumps([{
        "path": str(env.workspace / "secret-plan.txt"),
        "action": "create",
        "reason": "ttl contract test",
        "old_content": "",
        "new_content": "content",
    }])
    verdict = agent_adapter.propose(env, payload_text=payload)
    proposal = verdict["proposals"][0]
    assert proposal["state"] == "APPROVAL_REQUIRED"

    response = agent_adapter.approve(env)
    assert response["count"] == 1
    assert response["granted"][0]["ttl_seconds"] == APPROVAL_TTL_SECONDS

    ledger_path = (
        tanuq_dir(env.workspace) / "data" / "approval_ledger.jsonl"
    )
    grants = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    grants = [r for r in grants if r.get("record_type") == "grant"]
    assert grants, "no grant record persisted"
    record = grants[-1]
    assert record["expires_at"], "TTL not bound: expires_at is empty"

    fmt = "%Y-%m-%dT%H:%M:%SZ"
    created = datetime.strptime(record["created_at"], fmt).replace(
        tzinfo=timezone.utc
    )
    expires = datetime.strptime(record["expires_at"], fmt).replace(
        tzinfo=timezone.utc
    )
    assert (expires - created).total_seconds() == APPROVAL_TTL_SECONDS


# --- B/C) expiry validation ----------------------------------------------


def test_unexpired_approval_is_released_b():
    store = ApprovalStore()
    approval = store.grant(
        patch_fingerprint=FP,
        path="demo.txt",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        authorizer="test",
        expires_at=iso_in_future(APPROVAL_TTL_SECONDS),
    )
    assert approval.expires_at
    released = store.find_valid(
        FP,
        path="demo.txt",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        patch=_patch(),
    )
    assert released is not None
    assert released.approval_id == approval.approval_id


def test_expired_approval_is_rejected_c():
    store = ApprovalStore()
    store.grant(
        patch_fingerprint=FP,
        path="demo.txt",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        authorizer="test",
        expires_at=iso_in_past(5),
    )
    assert (
        store.find_valid(
            FP,
            path="demo.txt",
            action="modify",
            risk_level="HIGH",
            attempt=1,
            patch=_patch(),
        )
        is None
    )

    expired = Approval.create(
        patch_fingerprint=FP,
        path="demo.txt",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        authorizer="test",
        expires_at=iso_in_past(5),
    )
    valid, reason = is_approval_valid(expired, _patch(), "HIGH", 1)
    assert valid is False
    assert "expired" in reason.lower()


# --- D) durability: expiry survives ledger reload ------------------------


def test_persisted_expiry_survives_ledger_reload_d(tmp_path):
    ledger_path = tmp_path / "approval_ledger.jsonl"
    store = ApprovalStore(ledger=ApprovalLedger(path=str(ledger_path)))
    store.grant(
        patch_fingerprint=FP,
        path="demo.txt",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        authorizer="test",
        expires_at=iso_in_past(5),
    )

    reloaded = ApprovalStore(ledger=ApprovalLedger(path=str(ledger_path)))
    assert (
        reloaded.find_valid(
            FP,
            path="demo.txt",
            action="modify",
            risk_level="HIGH",
            attempt=1,
            patch=_patch(),
        )
        is None
    )


# --- E) fingerprint binding remains intact --------------------------------


def test_fingerprint_binding_remains_intact_e():
    store = ApprovalStore()
    store.grant(
        patch_fingerprint=FP,
        path="demo.txt",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        authorizer="test",
        expires_at=iso_in_future(APPROVAL_TTL_SECONDS),
    )
    assert (
        store.find_valid(
            OTHER_FP,
            path="demo.txt",
            action="modify",
            risk_level="HIGH",
            attempt=1,
            patch=_patch(fingerprint=OTHER_FP),
        )
        is None
    )
    approval = Approval.create(
        patch_fingerprint=OTHER_FP,
        path="demo.txt",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        authorizer="test",
        expires_at=iso_in_future(APPROVAL_TTL_SECONDS),
    )
    valid, reason = is_approval_valid(approval, _patch(), "HIGH", 1)
    assert valid is False
    assert "fingerprint" in reason.lower()


# --- F) single-use remains intact -----------------------------------------


def test_single_use_remains_intact_f():
    store = ApprovalStore()
    store.grant(
        patch_fingerprint=FP,
        path="demo.txt",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        authorizer="test",
        expires_at=iso_in_future(APPROVAL_TTL_SECONDS),
    )
    patch = _patch()
    first = store.find_valid(
        FP,
        path="demo.txt",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        patch=patch,
    )
    assert first is not None
    second = store.find_valid(
        FP,
        path="demo.txt",
        action="modify",
        risk_level="HIGH",
        attempt=1,
        patch=patch,
    )
    assert second is None
