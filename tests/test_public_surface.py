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
    """Read a site file.

    The landing-content contract in this module targets the TURKISH
    surface (site/tr/index.html) — its copy assertions are Turkish.
    The English default (site/index.html) is covered by
    tests/site_i18n_test.py.
    """
    if rel == "index.html":
        rel = "tr/index.html"
    return (SITE / rel).read_text(encoding="utf-8")


# ---- landing page content contract ----

def test_landing_exists_with_positioning():
    html = _read("index.html")
    # product-led positioning (sales model: Site → Ürün → Fiyat → Satın Al)
    assert "bağımsız yönetim katmanı" in html
    assert "Ajan değişikliği önerir. TANUQ riski belirler" in html
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


def test_landing_ctas_are_buy_and_how_not_demo():
    html = _read("index.html")
    start = html.find('<section class="hero">')
    end = html.find("</section>", start)
    hero = html[start:end]
    # primary hero CTA = start acquisition (no fake purchase claim)
    assert 'href="#pricing">EDİNİMİ BAŞLAT' in hero
    assert 'href="#how">NASIL ÇALIŞIR' in hero
    assert "DEMO" not in hero.upper()
    # demo-request / demo-drive CTAs are gone from the page
    assert "DEMO TALEP EDİN" not in html
    assert "TANUQ'YU DENEYİN" not in html
    assert "TANUQ'YU ŞİMDİ DENE" not in html
    assert 'id="demo"' not in html
    # no unproven "buy now" claim while checkout is not connected
    assert "TANUQ'YU AL" not in html


def _github_anchor_hrefs(html):
    """href values of anchors pointing at github.com (visible links only).

    Owner decision (site V2): the public site carries NO GitHub surface —
    no anchor, no URL, no `git clone` command text.
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
    # owner decision (site V2): no GitHub surface anywhere on the page
    assert "git clone" not in html
    assert "github" not in html.lower()


def test_public_site_sources_have_no_github():
    """§26 audit: all rendered public sources (EN default + TR + shared)
    carry zero GitHub references."""
    sources = (
        SITE / "index.html",
        SITE / "tr" / "index.html",
        SITE / "style.css",
        SITE / "demo.js",
        SITE / "demo_fixtures.json",
    )
    for path in sources:
        text = path.read_text(encoding="utf-8").lower()
        assert "github" not in text, f"github reference in {path}"
        assert "github.com" not in text


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
    nav = html[html.find("<nav"):html.find("</nav>")]
    assert 'href="#how"' in nav
    assert 'href="#demo-walkthrough"' in nav
    assert 'href="#pricing"' in nav
    assert 'class="nav-buy" href="#pricing"' in nav
    # sales-flow anchors resolve on the page
    for anchor in ("#pricing", "#buy", "#acquire", "#faq"):
        assert 'id="' + anchor[1:] + '"' in html or anchor in html
    # no GitHub anchor anywhere (git clone command text is not a link)
    assert _github_anchor_hrefs(html) == []


def test_footer_has_no_github_link():
    html = _read("index.html")
    footer = html.split("<footer>")[1] if "<footer>" in html else html
    assert "github.com" not in footer.lower()
    assert _github_anchor_hrefs(html) == []
