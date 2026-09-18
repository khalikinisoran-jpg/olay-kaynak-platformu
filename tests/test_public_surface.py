"""Public product surface (site/) tests.

The landing page must answer what/who/problem/how/try without
overstating proven capabilities, and the TRY TANUQ demo must drive the
REAL governed pipeline (no fake/simulated success) in a disposable
workspace with cleanup.
"""
import glob
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"


def _read(rel):
    return (SITE / rel).read_text(encoding="utf-8")


# ---- landing page content contract ----


def test_landing_exists_with_positioning():
    html = _read("index.html")
    assert "Swap the agent. Keep the control." in html
    assert "independent governance layer for AI coding agents" in html
    assert "Agents and models change. The governance contract doesn't." in html
    # agent-independence without model-list positioning
    assert "Any agent that can run a shell command" in html


def test_landing_shows_full_governed_flow():
    html = _read("index.html")
    for step in ("Proposal", "Risk", "Approval", "Execute", "Verify", "Evidence"):
        assert step in html
    # honest evidence wording: tamper-evident, explicitly not tamper-proof
    assert "tamper-evident" in html
    assert "not tamper-proof" in html


def test_landing_separates_try_connect_generic():
    html = _read("index.html")
    assert "TRY TANUQ" in html
    assert "CONNECT YOUR AGENT" in html
    assert "GENERIC CONTRACT" in html
    assert "tanuq propose --stdin-json --json" in html
    # connect is convenience, not a requirement
    assert "Optional" in html or "optional" in html


def test_landing_roadmap_is_labeled_as_research():
    html = _read("index.html")
    assert "under research" in html.lower()
    for future in ("Trajectory governance", "Anomaly / escape detection",
                   "Multi-agent governance"):
        assert future in html


def test_landing_links_github_and_has_no_tracking():
    html = _read("index.html")
    assert "github.com/khalikinisoran-jpg/olay-kaynak-platformu" in html
    # static site: no external scripts, no analytics, no tracking pixels
    assert "<script src=\"http" not in html
    assert "google-analytics" not in html.lower()
    assert "gtag" not in html.lower()


def test_honest_limits_present():
    html = _read("index.html")
    assert "No OS sandbox" in html
    assert "no network enforcement" in html
    assert "through Tanuq" in html


# ---- try scripts drive the real governed pipeline ----


def test_try_scripts_use_real_pipeline_and_cleanup():
    for script in ("try/try_tanuq.ps1", "try/try_tanuq.sh"):
        s = _read(script)
        # real governed CLI steps (no fake/simulated success markers)
        assert "-m tanuq" in s or "python -m tanuq" in s
        assert "propose" in s and "--stdin-json" in s
        assert "approve" in s
        assert "execute" in s
        assert "verify" in s
        assert "history" in s
        # disposable workspace + cleanup
        assert "tanuq-try-" in s
        assert "Cleanup" in s or "cleanup" in s
        assert "OVERALL PASS" in s


def test_try_scripts_have_no_simulated_success():
    for script in ("try/try_tanuq.ps1", "try/try_tanuq.sh"):
        s = _read(script)
        low = s.lower()
        # the demo must never fabricate governance outcomes
        assert "fake" not in low or "fake-output" not in low
        assert "simulate" not in low
        assert "mock" not in low


# ---- real end-to-end demo run (windows powershell) ----


@pytest.mark.skipif(os.name != "nt", reason="PowerShell demo on Windows")
def test_try_tanuq_powershell_runs_real_governed_pipeline():
    script = SITE / "try" / "try_tanuq.ps1"
    # housekeeping: remove leftovers from any previous failed attempts
    for leftover in glob.glob(os.path.join(
            os.environ.get("TEMP", os.environ.get("TMP", "")),
            "tanuq-try-*")):
        import shutil
        shutil.rmtree(leftover, ignore_errors=True)
    env = {**os.environ, "PYTHONPATH": str(REPO),
           "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        ["powershell", "-ExecutionPolicy", "Bypass",
         "-File", str(script)],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=600, env=env, cwd=str(REPO))
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"demo failed:\n{out[-2000:]}"
    assert "OVERALL PASS" in out
    # every governed stage really happened
    for marker in ("PROPOSED (LOW)", "APPROVAL_REQUIRED (HIGH)", "APPROVED",
                   "VERIFIED", "SINGLE-USE BINDING", "EVIDENCE"):
        assert marker in out
    assert "Evidence chain:" in out and "VALID" in out
    # disposable cleanup really removed the workspace
    assert "Cleanup: disposable workspace removed." in out
    leftovers = glob.glob(os.path.join(
        os.environ.get("TEMP", os.environ.get("TMP", "")), "tanuq-try-*"))
    assert leftovers == [], f"demo left workspaces behind: {leftovers}"


@pytest.mark.skipif(os.name == "nt", reason="bash demo on posix")
def test_try_tanuq_bash_runs_real_governed_pipeline():
    script = SITE / "try" / "try_tanuq.sh"
    env = {**os.environ, "PYTHONPATH": str(REPO),
           "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.run(
        ["bash", str(script)],
        capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=600, env=env, cwd=str(REPO))
    out = proc.stdout + proc.stderr
    assert proc.returncode == 0, f"demo failed:\n{out[-2000:]}"
    assert "OVERALL PASS" in out
