"""Global i18n contract for the public site (V1).

Owner decision: English is the DEFAULT language (`site/index.html`,
`<html lang="en">`) and Turkish is preserved at `site/tr/index.html`
(`<html lang="tr">`) with a language switch in both navigations.

Static-hosting fact: `/tr/` is a plain directory index
(`tr/index.html`) — any static file server maps it without routing
rules; no other routing behavior is promised.

Covers (§22):
1 default language = English      6 forbidden claims = 0 (both)
2 Turkish route exists            7 demo error strings = 0 (both)
3 language switch works           8 pricing truth in both
4 core sections in both           9 no fake purchase CTA (both)
5 GitHub = 0 in both             10 layout markers/parity (static part)

Read-only static-content test. No core files, no fixtures modified,
no deployment.
"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"
EN_PATH = SITE / "index.html"
TR_PATH = SITE / "tr" / "index.html"
DEMO_JS = SITE / "demo.js"
FIXTURE = SITE / "demo_fixtures.json"


def _en():
    return EN_PATH.read_text(encoding="utf-8")


def _tr():
    return TR_PATH.read_text(encoding="utf-8")


def _nav(page):
    return page[page.index("<nav"):page.index("</nav>")]


def _github_anchors(page):
    return [
        m.group(1)
        for m in re.finditer(r'<a\b[^>]*?href\s*=\s*"([^"]+)"', page, re.I)
        if "github.com" in m.group(1).lower()
    ]


SECTION_MARKERS = [
    '<section class="hero">',
    '<section class="section problem"',
    'id="how"',
    'id="demo-walkthrough"',
    'class="section value"',
    'id="features"',
    'class="section statement"',
    'id="trust"',
    'class="section who',
    'class="section product"',
    'id="pricing"',
    'id="acquire"',
    'id="try"',
    'id="faq"',
    'class="section cta-final"',
]

FORBIDDEN_CLAIMS = (
    # English
    "all agents", "every agent", "hundreds of agents", "works with any agent",
    "all models", "every model", "enterprise ready", "production proven",
    "zero trust", "compliance", "certification", "benchmark", "guaranteed",
    "completely secure", "completely protected", "instant access",
    "five minutes", "5 minutes", "cheaper", "savings", "build vs buy",
    "build it yourself", "buy now",
    # Turkish
    "tüm agent", "her ajanla", "her agent", "yüzlerce agent", "tüm model",
    "tüm modeller", "enterprise ready", "production proven", "zero trust",
    "compliance", "sertifika", "benchmark", "garantili", "tamamen güvenli",
    "tam koruma", "anında erişim", "5 dakika", "daha ucuz", "tasarruf",
    "build vs buy", "kendiniz geliştirm", "çalışabilecek bağımsız",
    "satın al", "tanuq'yu al",
)

DEMO_ERROR_STRINGS = (
    "Walkthrough unavailable",
    "Failed to fetch",
    "Could not load",
    "Serve site",
)

PROOF_VALUES = (
    "deploy_demo.py",
    "HIGH",
    "864c6050",
    "06d0ba48d949",
    "VERIFIED",
    "chain VALID",
    "events 11",
    "recorded_real_run",
)

FAKE_PURCHASE_LABELS = (
    "BUY NOW", "PURCHASE", "GET IT NOW", "SATIN AL", "TANUQ'YU AL",
    "HEMEN SATIN AL",
)


# ---- 1 / 2: default language and Turkish route ----

def test_default_document_is_english():
    en = _en()
    assert '<html lang="en">' in en
    assert "An independent governance layer for AI coding agents" in en
    assert "An independent governance layer" in en  # hero H1
    assert "governance layer" in en  # meta description
    # Turkish-only UI copy must not leak into the English default
    for tr_only in ("EDİNİMİ BAŞLAT", "Nasıl Çalışır", "Kontrol sizde kalsın"):
        assert tr_only not in en, f"Turkish copy leaked into EN: {tr_only}"


def test_turkish_route_exists_and_is_turkish():
    assert TR_PATH.exists(), "site/tr/index.html missing (Turkish route)"
    tr = _tr()
    assert '<html lang="tr">' in tr
    # Turkish content preserved (not lost in the EN default switch)
    assert "bağımsız yönetim katmanı" in tr
    assert "son karar kimde" in tr
    assert "Kurulum ve kullanım akışı" in tr
    assert "Edinmeden önce" in tr
    # subpath-relative asset resolution (/tr/ directory index)
    assert 'href="../style.css"' in tr
    assert 'src="../demo.js"' in tr
    assert 'data-fixture="../demo_fixtures.json"' in tr
    assert 'src="../assets/tanuq-logo-header-sm.png"' in tr


# ---- 3: language switch ----

def test_language_switch_present_in_both_navigations():
    en_nav, tr_nav = _nav(_en()), _nav(_tr())
    assert 'class="lang-switch" href="tr/index.html"' in en_nav
    assert ">TR</a>" in en_nav
    assert 'class="lang-switch" href="../index.html"' in tr_nav
    assert ">EN</a>" in tr_nav


# ---- 4 / parity: core sections in both ----

def test_core_sections_present_in_both_languages():
    en, tr = _en(), _tr()
    for marker in SECTION_MARKERS:
        assert marker in en, f"EN missing section: {marker}"
        assert marker in tr, f"TR missing section: {marker}"
    # identical information hierarchy in both languages
    assert [en.index(m) for m in SECTION_MARKERS] == sorted(
        en.index(m) for m in SECTION_MARKERS)
    assert [tr.index(m) for m in SECTION_MARKERS] == sorted(
        tr.index(m) for m in SECTION_MARKERS)


def test_strategic_positioning_present_in_both():
    line = "Agent intelligence is replaceable. Governance state is not."
    assert line in _en()
    assert line in _tr()


# ---- 5: GitHub = 0 in both ----

def test_github_zero_in_both_languages():
    for page in (_en(), _tr()):
        assert "github" not in page.lower()
        assert "git clone" not in page.lower()
        assert _github_anchors(page) == []


# ---- 6: forbidden claims = 0 in both ----

def test_forbidden_claims_zero_in_both_languages():
    for page in (_en(), _tr()):
        low = page.lower()
        for phrase in FORBIDDEN_CLAIMS:
            # word-boundary match so "other agent" != forbidden "her agent"
            pattern = r"\b" + re.escape(phrase) + r"\b"
            assert not re.search(pattern, low), \
                f"forbidden claim present: {phrase}"


# ---- 7: demo error strings = 0 ----

def test_demo_error_strings_zero_in_both_languages():
    demo_js = DEMO_JS.read_text(encoding="utf-8")
    for page in (_en(), _tr()):
        for text in DEMO_ERROR_STRINGS:
            assert text not in page, f"demo error string in page: {text}"
            assert text not in demo_js, f"demo error string in demo.js: {text}"


# ---- 8: pricing truth in both ----

def test_pricing_truth_in_both_languages():
    en, tr = _en(), _tr()
    assert "$49" in en and "/ month" in en
    assert "launch pricing" in en
    assert "Payment and licensing infrastructure is not yet live" in en
    assert "$49" in tr and "/ ay" in tr
    assert "lansman öncesi" in tr
    assert "açılmamıştır" in tr
    # no fake checkout machinery in either page
    for page in (en, tr):
        assert "<form" not in page.lower()
        assert "<input" not in page.lower()


# ---- 9: no fake purchase CTA ----

def test_no_fake_purchase_cta_in_both_languages():
    en, tr = _en(), _tr()
    for page in (en, tr):
        for label in FAKE_PURCHASE_LABELS:
            assert label not in page, f"fake purchase CTA present: {label}"
        anchor_texts = re.findall(r"<a[^>]*>([^<]*)</a>", page)
        for text in anchor_texts:
            up = text.upper()
            assert not any(w in up for w in ("BUY", "PURCHASE", "SATIN")), text
    # honest primary CTA exists in both
    assert 'href="#pricing">START ACQUISITION' in en
    assert 'href="#pricing">EDİNİMİ BAŞLAT' in tr


# ---- proof parity: real capture values in both ----

def test_real_proof_values_in_both_languages():
    for page in (_en(), _tr()):
        for marker in PROOF_VALUES:
            assert marker in page, f"proof value missing: {marker}"


# ---- integration claims stay limited in both ----

def test_integrations_stated_limited_in_both_languages():
    en, tr = _en(), _tr()
    assert "official Claude Code adapter" in en
    assert "not yet validated" in en
    assert "resmi adaptör" in tr
    assert "henüz doğrulanmamıştır" in tr


# ---- shared walkthrough assets resolve for both pages ----

def test_walkthrough_assets_exist_for_both_languages():
    assert 'id="demo-root"' in _en() and 'id="demo-root"' in _tr()
    assert 'data-fixture="demo_fixtures.json"' in _en()
    assert DEMO_JS.exists()
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["source"]["type"] == "recorded_real_run"
    assert fixture["scenario"]["risk"] == "HIGH"
