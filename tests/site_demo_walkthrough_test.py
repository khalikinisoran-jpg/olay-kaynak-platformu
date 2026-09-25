"""Walkthrough fixture contract for the recorded HIGH happy-path demo.

Validates site/demo_fixtures.json only — no browser automation, no UI.
Values must derive from a single recorded_real_run capture (not stitched).
"""
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURE = REPO / "site" / "demo_fixtures.json"

FP = "06d0ba48d949c653cceddde7fa3f99629034e7e80fd635cf30e8b9b0373feb77"
OP = "8f363a75-d1b3-46bc-9c3c-cc333c7cf6b0"
APPROVAL = "864c6050"


def _load():
    assert FIXTURE.exists(), "demo fixture missing"
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _steps_by_id(data):
    return {s["id"]: s for s in data["steps"]}


def test_fixture_exists_and_parses():
    data = _load()
    assert isinstance(data, dict)
    assert data["steps"], "steps required"


def test_source_is_recorded_real_run():
    data = _load()
    src = data["source"]
    assert src["type"] == "recorded_real_run"
    assert src.get("operation_id") == OP
    assert "capture" in src and src["capture"]


def test_scenario_risk_is_high():
    data = _load()
    assert data["scenario"]["risk"] == "HIGH"


def test_approval_required_present():
    data = _load()
    steps = _steps_by_id(data)
    assert steps["propose"]["state"] == "APPROVAL_REQUIRED"
    assert steps["approval_required"]["state"] == "APPROVAL_REQUIRED"
    assert steps["propose"]["data"]["approval_required"] is True


def test_approval_present():
    data = _load()
    steps = _steps_by_id(data)
    assert steps["approve"]["state"] == "APPROVED"
    assert steps["approve"]["data"]["approval_id"] == APPROVAL
    assert steps["approve"]["data"]["single_use"] is True


def test_fingerprint_present_and_consistent():
    data = _load()
    steps = _steps_by_id(data)
    assert data["integrity"]["fingerprint"] == FP
    assert steps["propose"]["data"]["fingerprint"] == FP
    for sid in ("propose", "policy", "approval_required", "approve", "execute", "verify"):
        short = steps[sid]["data"].get("fingerprint_short")
        assert short == FP[:12], f"{sid} fingerprint_short mismatch"
    assert data["integrity"]["identity_consistency"]["propose_approve_execute_lineage"] == FP


def test_execute_applied_present():
    data = _load()
    steps = _steps_by_id(data)
    assert steps["execute"]["state"] == "APPLIED"
    assert steps["execute"]["data"]["apply_success"] is True
    assert steps["execute"]["data"]["intent_id"] == OP


def test_verified_present():
    data = _load()
    steps = _steps_by_id(data)
    assert steps["verify"]["state"] == "VERIFIED"
    assert steps["verify"]["data"]["terminal_state"] == "VERIFIED"
    assert steps["verify"]["data"]["verification_passed"] is True
    assert data["integrity"]["verification"] == "VERIFIED"


def test_evidence_chain_valid_present():
    data = _load()
    steps = _steps_by_id(data)
    ev = steps["evidence"]["data"]
    assert ev["chain"] == "VALID"
    assert ev["anchor"] == "ACTIVE"
    assert ev["approval_ledger"] == "VALID"
    assert ev["events_in_chain"] == 11
    assert data["integrity"]["evidence"]["chain"] == "VALID"


def test_run_identity_present():
    data = _load()
    assert data["source"]["operation_id"] == OP
    assert data["integrity"]["approval"] == APPROVAL
    assert data["integrity"]["fingerprint"] == FP
