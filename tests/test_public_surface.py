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


# ---- landing page content contract (product/sales V2) ----


def test_landing_exists_with_positioning():
    html = _read("index.html")
    assert "Yapay zekâ kodlama ajanları hızla çalışır" in html
    assert "Kontrolünüz kaybolmamalı" in html
    assert "bağımsız bir yönetim katmanı" in html


def test_landing_problem_speaks_customer_language():
    html = _read("index.html")
    assert "Agent'ın ne yapabileceğini kim kontrol ediyor?" in html
    assert "doğrudan diske yazılıyor" in html


def test_landing_solution_pipeline_complete():
    html = _read("index.html")
    for node in ("AJANINIZ", "TANUQ", "KODUNUZ"):
        assert node in html
    for step in ("Risk", "Approval", "Execute", "Verify", "Evidence"):
        assert step in html
    assert "otomatik geri alınır" in html


def test_landing_benefits_use_customer_outcomes():
    html = _read("index.html")
    for b in ("CONTROL", "VISIBILITY", "VERIFICATION", "EVIDENCE",
              "VENDOR INDEPENDENCE"):
        assert b in html
    assert "Riskli değişikliklerde karar sizde kalır" in html
    assert "yönetim sözleşmeniz değişmez" in html


def test_landing_shows_real_terminal_output_not_fake():
    html = _read("index.html")
    assert "terminal state: VERIFIED" in html
    assert "Verification passed: True" in html
    assert "risk=HIGH single-use" in html
    assert "gerçek bir TANUQ çalışmasından alınmıştır" in html


def test_landing_ctas_are_try_and_demo_not_github():
    html = _read("index.html")
    assert "TANUQ'YU DENEYİN" in html
    assert "DEMO TALEP EDİN" in html
    # GitHub is NOT a hero CTA: hero links only #try and #demo
    hero = html.split("</header>")[0]
    assert "github.com" not in hero


def test_landing_separates_try_connect_generic():
    html = _read("index.html")
    assert "Kendi makinenizde görün" in html
    assert "yönetim sözleşmeniz değişmez" in html
    assert "tanuq propose --stdin-json --json" in html
    # generic path works without connect
    assert "bağlantı adımı" in html
    assert "vendor kilitlenmesi yok" in html
    assert "kurulum zorunlu değildir" in html.lower()


def test_no_future_roadmap_on_page():
    """Hayal satmayalim: sayfa yalnizca bugun dogrulanmis kabiliyetleri
    gostermeli; gelecek vizyonu urun ozelligi gibi sunulmamali."""
    html = _read("index.html").lower()
    assert "roadmap" not in html
    assert "araştırma aşamasında" not in html
    assert "trajectory governance" not in html
    assert "kaçış tespiti" not in html
    assert "çoklu-ajan yönetimi" not in html
    assert "anomali" not in html


def test_landing_links_github_and_has_no_tracking():
    html = _read("index.html")
    assert "github.com/khalikinisoran-jpg/olay-kaynak-platformu" in html
    # static site: no external scripts, no analytics, no tracking pixels
    assert '<script src="http' not in html
    assert "google-analytics" not in html.lower()
    assert "gtag" not in html.lower()


def test_honest_limits_present_not_in_hero():
    html = _read("index.html")
    limits_pos = html.find('id="limits"')
    hero_pos = html.find("</header>")
    assert 0 < hero_pos < limits_pos
    assert "tanuq üzerinden gelen" in html
    assert "İşletim sistemi seviyesinde koruma yok" in html
    assert "ağ zorlaması yok" in html


def test_no_misspelling_or_forbidden_terms():
    html = _read("index.html")
    assert "TANUK" not in html
    assert "temsilci" not in html
    assert "tamper-proof" not in html


def test_no_fake_contact_form():
    html = _read("index.html")
    assert "<form" not in html
    assert "<input" not in html.lower()


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
