"""Static UI wiring tests for the execute action (Phase 1).

The UI is a view layer only: the Execute button must call the existing
/api/execute endpoint (no new backend, no new authority) and surface
the result. Static-content assertions keep this wiring from
regressing; behavioural coverage lives in test_tanuq_web.py.
"""
import os


def _app_js():
    here = os.path.dirname(__file__)
    with open(os.path.join(here, os.pardir, "tanuq", "static", "app.js"),
              "rb") as f:
        return f.read().decode("utf-8")


def test_app_js_wires_execute_to_api():
    js = _app_js()
    assert 'data-action="execute"' in js
    assert "/api/execute" in js
    assert "function execute(" in js


def test_app_js_execute_shows_result_and_refreshes_pending():
    js = _app_js()
    assert "terminal" in js
    assert "apply_success" in js
    assert "verification_passed" in js
    assert "pending_count" in js
    assert "show('pending')" in js


def test_reject_and_approve_flows_untouched():
    js = _app_js()
    assert "async function reject(fp)" in js
    assert "async function approve(fp)" in js
