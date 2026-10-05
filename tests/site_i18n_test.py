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

Retired (Owner-approved): spec items 2 (Turkish route) and 3 (language
switch) — after the B-min decision `/tr/` serves a static redirect
page; those guarantees live in `tests/site_tr_redirect_test.py`.
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


def _segment(page, marker):
    start = page.index(marker)
    return page[start:page.index("</section>", start)]


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
    'id="feedback"',
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
    # old pricing / sales model leftovers (FREE strategy)
    "$49", "$19", "/ month", "/ ay", "one-time", "tek seferlik",
    "launch pricing", "lansman öncesi", "acquisition", "checkout",
    "start acquisition", "purchase",
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
    "HEMEN SATIN AL", "START ACQUISITION", "EDİNİMİ BAŞLAT",
)


# ---- 1 / 2: default language and Turkish route ----

def test_default_document_is_english():
    en = _en()
    assert '<html lang="en">' in en
    assert "An independent governance layer for AI coding agents" in en
    assert "An independent governance layer" in en  # hero H1
    assert "governance layer" in en  # meta description
    # Turkish-only UI copy must not leak into the English default
    for tr_only in ("TANUQ ücretsizdir", "Nasıl Çalışır", "Kontrol sizde kalsın"):
        assert tr_only not in en, f"Turkish copy leaked into EN: {tr_only}"
    # free message present on the EN default
    assert "TANUQ is free to use" in en


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
            # word-edge match so "other agent" != forbidden "her agent",
            # and so "$49" / "/ month" (non-word edges) still match
            pattern = r"(?<!\w)" + re.escape(phrase) + r"(?!\w)"
            assert not re.search(pattern, low), \
                f"forbidden claim present: {phrase}"


# ---- 7: demo error strings = 0 ----

def test_demo_error_strings_zero_in_both_languages():
    demo_js = DEMO_JS.read_text(encoding="utf-8")
    for page in (_en(), _tr()):
        for text in DEMO_ERROR_STRINGS:
            assert text not in page, f"demo error string in page: {text}"
            assert text not in demo_js, f"demo error string in demo.js: {text}"


# ---- 8: FREE pricing truth in both ----

def test_pricing_truth_in_both_languages():
    en, tr = _en(), _tr()
    # EN free surface
    assert "FREE" in _segment(en, 'id="pricing"')
    assert "free to use" in en
    assert "Future pricing has not been decided" in en
    # TR free surface
    assert "ÜCRETSİZ" in _segment(tr, 'id="pricing"')
    assert "TANUQ ücretsizdir" in tr
    assert "fiyatlandırma henüz belirlenmedi" in tr
    # old price model and checkout language completely gone
    for page in (en, tr):
        low = page.lower()
        for leftover in ("$49", "$19", "/ month", "/ ay", "checkout",
                         "purchase", "start acquisition", "launch pricing"):
            assert leftover not in low, f"sales leftover present: {leftover}"
        assert "<form" not in low
        assert "<input" not in low


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
    # honest primary CTA exists in both (start using, not buying)
    assert 'href="#acquire">START USING TANUQ' in en
    assert 'href="#acquire">TANUQ\'U KULLAN' in tr
    assert 'id="get" href="#acquire"' in en
    assert 'id="get" href="#acquire"' in tr


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


# ---- feedback channel: honest in both languages, no invented channel ----

def test_feedback_channel_is_honest_in_both_languages():
    en, tr = _en(), _tr()
    fe = _segment(en, 'id="feedback"')
    ft = _segment(tr, 'id="feedback"')
    # required call-to-action copy (§3/§7), per language
    assert "Tried TANUQ? Tell us what happened." in fe
    assert "TANUQ'u denedin mi?" in ft
    assert "Send your experience directly to the TANUQ team" in fe
    assert "Deneyimini doğrudan TANUQ ekibine gönder" in ft
    # five prompts in both languages
    assert fe.count("<h3>") == 5
    assert ft.count("<h3>") == 5
    # REAL channel wired exactly once per page, inside the feedback block
    assert en.count("mailto:feedback@tanuq.net") == 1
    assert tr.count("mailto:feedback@tanuq.net") == 1
    assert fe.count("mailto:feedback@tanuq.net") == 1
    assert ft.count("mailto:feedback@tanuq.net") == 1
    # encoded subject + body (spaces/newlines/turkish chars safe)
    assert "subject=TANUQ%20Feedback" in fe
    assert "subject=TANUQ%20Geri%20Bildirim" in ft
    assert "body=" in fe and "%0A" in fe
    assert "body=" in ft and "%0A" in ft
    assert "SEND FEEDBACK" in fe
    assert "GERİ BİLDİRİM GÖNDER" in ft
    # old "no channel yet" copy is gone
    assert "public contact channel on this page yet" not in en
    assert "herkese açık iletişim kanalı yok" not in tr
    # privacy honesty preserved; no auto-collection claim
    assert "no tracking" in fe and "no analytics" in fe
    assert "izleme yok" in ft and "analytics yok" in ft
    for page in (en, tr):
        low = page.lower()
        assert "automatically collected" not in low
        # no fake form/backend; GitHub stays out of the public surface
        assert "<form" not in low and "<input" not in low
        assert "github" not in low
