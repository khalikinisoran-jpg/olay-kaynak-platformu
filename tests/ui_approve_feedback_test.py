"""Approve-feedback UI wiring tests (Phase 2 / operator-flow polish).

Real dogfood finding: a successful Approve click re-rendered the
pending list with no visible change, so the operator believed the
button did nothing. These static-content assertions pin the view-layer
feedback: APPROVED badge, disabled re-approve, error card.
Behavioural coverage lives in test_tanuq_web.py.
"""
import os


def _app_js():
    here = os.path.dirname(__file__)
    with open(os.path.join(here, os.pardir, "tanuq", "static", "app.js"),
              "rb") as f:
        return f.read().decode("utf-8")


def test_session_approved_state_exists():
    js = _app_js()
    assert "const approved = new Set()" in js


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


def test_pending_state_badge_conditional():
    js = _app_js()
    assert "approved.has(p.fingerprint)" in js
