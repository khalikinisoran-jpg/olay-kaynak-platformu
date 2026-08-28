import json

import pytest

from simulation.agent.approval.approval import (
    Approval,
    iso_in_past,
)

from simulation.agent.approval.approval_ledger import (
    ApprovalLedger,
)

from simulation.agent.approval.approval_store import (
    ApprovalStore,
)

from simulation.agent.worker.patch_proposal import (
    PatchProposal
)


def make_patch(tmp_path, marker="value = 2\n"):

    target = tmp_path / "settings.secret.txt"

    target.parent.mkdir(parents=True, exist_ok=True)

    original = "value = 1\n"

    target.write_text(original, encoding="utf-8")

    return PatchProposal(
        path=str(target),
        action="modify",
        reason="Approval durability test.",
        old_content=original,
        new_content=marker,
        allowed_paths=(str(target),),
    )


def make_ledger(tmp_path):

    return ApprovalLedger(
        path=tmp_path / "approval_ledger.jsonl"
    )


def test_consumed_approval_stays_consumed_after_restart(tmp_path):

    patch = make_patch(tmp_path)

    ledger = make_ledger(tmp_path)

    first = ApprovalStore(ledger=ledger)

    approval = first.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    released = first.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        patch=patch,
    )

    assert released is not None

    restarted = ApprovalStore(
        ledger=make_ledger(tmp_path)
    )

    again = restarted.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        patch=patch,
    )

    assert again is None

    assert restarted.is_consumed(approval) is True


def test_applied_approval_stays_applied_after_restart(tmp_path):

    patch = make_patch(tmp_path)

    first = ApprovalStore(
        ledger=make_ledger(tmp_path)
    )

    approval = first.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    released = first.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        patch=patch,
    )

    assert first.authorize_apply(
        released.approval_id,
        patch,
    ) is True

    restarted = ApprovalStore(
        ledger=make_ledger(tmp_path)
    )

    assert restarted.authorize_apply(
        approval.approval_id,
        patch,
    ) is False

    assert restarted.is_applied(approval) is True


def test_unconsumed_grant_survives_restart_and_rebinds(tmp_path):

    patch = make_patch(tmp_path)

    first = ApprovalStore(
        ledger=make_ledger(tmp_path)
    )

    first.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    restarted = ApprovalStore(
        ledger=make_ledger(tmp_path)
    )

    released = restarted.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        patch=patch,
    )

    assert released is not None

    twin = PatchProposal(
        path=patch.path,
        action=patch.action,
        reason=patch.reason,
        old_content=patch.old_content,
        new_content=patch.new_content,
        allowed_paths=patch.allowed_paths,
    )

    assert (
        restarted.authorize_apply(
            released.approval_id,
            twin,
        )
        is False
    )

    assert (
        restarted.authorize_apply(
            released.approval_id,
            patch,
        )
        is True
    )


def test_expired_approval_denied_after_restart(tmp_path):

    patch = make_patch(tmp_path)

    first = ApprovalStore(
        ledger=make_ledger(tmp_path)
    )

    first.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=iso_in_past(60),
    )

    restarted = ApprovalStore(
        ledger=make_ledger(tmp_path)
    )

    released = restarted.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        patch=patch,
    )

    assert released is None


def test_corrupted_ledger_fails_closed(tmp_path):

    patch = make_patch(tmp_path)

    first = ApprovalStore(
        ledger=make_ledger(tmp_path)
    )

    first.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    ledger_path = tmp_path / "approval_ledger.jsonl"

    ledger_path.write_text(
        "NOT JSON\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError):

        ApprovalStore(
            ledger=make_ledger(tmp_path)
        )


def test_tampered_ledger_fails_closed(tmp_path):

    patch = make_patch(tmp_path)

    first = ApprovalStore(
        ledger=make_ledger(tmp_path)
    )

    first.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    ledger_path = tmp_path / "approval_ledger.jsonl"

    records = [
        json.loads(line)
        for line in ledger_path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]

    records[0]["authorizer"] = "attacker"

    ledger_path.write_text(
        "\n".join(
            json.dumps(record)
            for record in records
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError):

        ApprovalStore(
            ledger=make_ledger(tmp_path)
        )


def test_ledger_chain_verifies_after_full_lifecycle(tmp_path):

    patch = make_patch(tmp_path)

    ledger = make_ledger(tmp_path)

    store = ApprovalStore(ledger=ledger)

    approval = store.grant(
        patch_fingerprint=patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        authorizer="human-1",
        expires_at=3600,
    )

    released = store.find_valid(
        patch.fingerprint(),
        path=patch.path,
        action=patch.action,
        risk_level="HIGH",
        attempt=1,
        patch=patch,
    )

    store.authorize_apply(
        released.approval_id,
        patch,
    )

    records = ledger.load()

    assert [
        record["record_type"]
        for record in records
    ] == [
        ApprovalLedger.TYPE_GRANT,
        ApprovalLedger.TYPE_CONSUMED,
        ApprovalLedger.TYPE_APPLIED,
    ]

    assert records[0]["approval_id"] == approval.approval_id
