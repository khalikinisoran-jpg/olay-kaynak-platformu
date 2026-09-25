"""Public product surface (site/) tests — updated for redesigned site.

Covers: landing content, logo asset, responsive layout markers,
CTA integrity, honest limits, and no-forbidden-terms contract.
"""
import json
import os

from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"


def _read(rel):
    return (SITE / rel).read_text(encoding="utf-8")


# ---- landing page content contract ----

def test_landing_exists_with_positioning():
    html = _read("index.html")
    assert "Yapay zekâ çalışsın" in html
    assert "Kontrol sizde kalsın" in html
    assert "güvenlik katmanı" in html


def test_landing_problem_speaks_customer_language():
    html = _read("index.html")
    assert "son karar kimde" in html
    assert "kontrol gerektirmez" in html or "kontrol gerektirir" in html


def test_landing_solution_six_steps():
    html = _read("index.html")
    for step in ("Öneri", "Değerlendirme", "Onay", "Uygulama",
                 "Doğrulama", "Kayıt"):
        assert step in html


def test_landing_benefits_use_customer_outcomes():
    html = _read("index.html")
    for b in ("CONTROL", "VISIBILITY", "VERIFICATION", "EVIDENCE"):
        assert b in html


def test_landing_shows_real_terminal_output_not_fake():
    html = _read("index.html")
    assert "APPROVAL_REQUIRED" in html
    assert "VERIFIED" in html
    assert "Propose" in html or "propose" in html


def test_landing_ctas_are_try_and_demo_not_github():
    html = _read("index.html")
    assert "TANUQ'YU DENEYİN" in html
    assert "DEMO TALEP EDİN" in html
    # GitHub is NOT a hero CTA; primary hero CTA = interactive demo
    hero = html.split("</header>")[0] + html[html.find("</header>"):html.find("</header>") + 500]
    assert "TANUQ'YU ŞİMDİ DENE" in hero
    assert "#demo-walkthrough" in hero


def _github_anchor_hrefs(html):
    """href values of anchors pointing at github.com (visible links only).

    Plain `git clone ...` command text in the LOCAL TRY section is NOT an
    anchor and must stay untouched.
    """
    import re
    return [
        m.group(1)
        for m in re.finditer(r'<a\b[^>]*?href\s*=\s*"([^"]+)"', html, re.I)
        if "github.com" in m.group(1).lower()
    ]


def test_no_visible_github_link_anywhere():
    html = _read("index.html")
    assert _github_anchor_hrefs(html) == [], \
        f"visible GitHub link(s) present: {_github_anchor_hrefs(html)}"
    # local installation command must stay
    assert "git clone" in html


def test_landing_has_no_github_link_and_no_tracking():
    html = _read("index.html")
    assert _github_anchor_hrefs(html) == []
    assert '<script src="http' not in html
    assert "google-analytics" not in html.lower()
    assert "gtag" not in html.lower()


def test_honest_limits_in_footer():
    html = _read("index.html")
    assert "tamper-evident" in html
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


def test_no_future_roadmap_on_page():
    html = _read("index.html").lower()
    assert "roadmap" not in html
    assert "trajectory governance" not in html
    assert "kaçış tespiti" not in html
    assert "çoklu-ajan yönetimi" not in html
    assert "anomali" not in html


def test_who_it_is_for_section():
    html = _read("index.html")
    assert "Kimler için" in html
    assert "AI coding agent kullanan ekipler" in html
    assert "Platform Engineering" in html
    assert "Security / DevSecOps" in html


# ---- logo asset contract ----

def test_logo_asset_exists():
    logo = SITE / "assets" / "tanuq-logo.png"
    assert logo.exists(), "original logo missing"
    header = SITE / "assets" / "tanuq-logo-header-sm.png"
    assert header.exists(), "header logo missing"
    transparent = SITE / "assets" / "tanuq-logo-transparent.png"
    assert transparent.exists(), "transparent logo missing"
    favicon = SITE / "assets" / "tanuq-favicon.png"
    assert favicon.exists(), "favicon missing"


def test_logo_referenced_in_html():
    html = _read("index.html")
    assert "tanuq-logo-header-sm.png" in html
    assert "tanuq-favicon.png" in html


# ---- CSS design system contract ----

def test_css_uses_logo_color_palette():
    css = _read("style.css")
    for color in ("#1B2A3E", "#2A9D8F", "#FFFFFF", "#F6F8FA", "#D8DEE4"):
        assert color.lower() in css.lower() or color in css, \
            f"logo color missing from CSS: {color}"


def test_css_has_responsive_breakpoints():
    css = _read("style.css")
    assert "max-width: 768px" in css
    assert "max-width: 390px" in css


def test_css_no_heavy_animations():
    css = _read("style.css")
    assert "animation:" not in css
    assert "@keyframes" not in css


# ---- try scripts still functional ----

def test_try_scripts_use_real_pipeline_and_cleanup():
    for script in ("try/try_tanuq.ps1", "try/try_tanuq.sh"):
        s = _read(script)
        assert "-m tanuq" in s or "python -m tanuq" in s
        assert "propose" in s and "--stdin-json" in s
        assert "approve" in s
        assert "execute" in s
        assert "verify" in s
        assert "history" in s
        assert "OVERALL PASS" in s


# ---- structural integrity ----

def test_nav_links_present():
    html = _read("index.html")
    assert "#how" in html
    assert "#try" in html
    assert "#demo" in html
    # no GitHub anchor anywhere (git clone command text is not a link)
    assert _github_anchor_hrefs(html) == []


def test_footer_has_no_github_link():
    html = _read("index.html")
    footer = html.split("<footer>")[1] if "<footer>" in html else html
    assert "github.com" not in footer.lower()
    assert _github_anchor_hrefs(html) == []
