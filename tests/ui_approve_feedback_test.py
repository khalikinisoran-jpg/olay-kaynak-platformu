"""Approve-feedback UI wiring tests (Phase 2 / operator-flow polish).

Real dogfood finding: a successful Approve click re-rendered the
pending list with no visible change, so the operator believed the
button did nothing. Phase 2.1 moved the APPROVED badge to server-side
approval metadata (reload-safe; the in-memory session Set was
removed). These static-content assertions pin that design:
server-metadata primary badge (granted/consumed/expired), disabled
re-approve, error card. Behavioural coverage lives in
test_tanuq_web.py.
"""
import os


def _app_js():
    here = os.path.dirname(__file__)
    with open(os.path.join(here, os.pardir, "tanuq", "static", "app.js"),
              "rb") as f:
        return f.read().decode("utf-8")


def test_server_metadata_badge_primary():
    js = _app_js()
    assert "(p.approval && p.approval.state === 'granted')" in js


def test_approved_card_shows_visible_feedback():
    js = _app_js()
    assert "APPROVED " in js or "APPROVED" in js
    assert "execute bekleniyor" in js


def test_duplicate_approve_guard_disabled_button():
    js = _app_js()
    assert "disabled" in js
    assert "Onaylandı" in js


def test_approve_error_feedback_visible():
    js = _app_js()
    assert "Approve failed" in js


def test_pending_state_badge_server_conditional():
    js = _app_js()
    assert "(p.approval && p.approval.state === 'granted')" in js
    assert "p.approval.state === 'consumed'" in js
    assert "p.approval.state === 'expired'" in js
