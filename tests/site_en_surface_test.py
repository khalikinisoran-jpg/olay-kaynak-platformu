"""TANUQ FREE — English surface contract (post B-min, EN-only site).

New module (G1): no existing test module is modified.

Context: per Owner decision the Turkish page is replaced by a static
redirect page (`site/tr/index.html`, covered by
`tests/site_tr_redirect_test.py`), and the EN default is the only
published content surface. The legacy TR-surface modules
(`site_i18n_test`, `site_sales_model_test`, `test_public_surface`,
`site_download_block_test`) still encode the old two-language contract
and are pending an Owner decision; this module restores the EN-only
assertions they used to carry, without touching them.

Covers:
1. EN section structure and order (static page contract).
2. EN navigation and primary CTAs (start-using, no purchase CTA).
3. EN pricing truth (FREE, no stale price model).
4. EN proof values from the recorded run.
5. EN integration-claim limits.
6. EN feedback channel honesty.
7. EN footer honest limits.
8. EN walkthrough asset wiring.
9. EN Windows-installer download block:
   - installer + checksum URLs present and correctly bound to <a href>;
   - expected SHA-256 present verbatim (exact match);
   - existing CSS/HTML classes only (no inline styles);
   - Windows 10/11 x64, per-user/no-admin, offline after install,
     no auto-update, unsigned + SmartScreen/Defender disclosures;
   - FAQ explains the installer download and install flow;
   - stale "not yet published" claim is absent.

Read-only static-content test: no deploy, no hosting change, no core
files.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"
EN_PATH = SITE / "index.html"

EXE_URL = "https://tanuq.net/downloads/TANUQ-Setup-0.6.0.exe"
SUMS_URL = "https://tanuq.net/downloads/SHA256SUMS.txt"
SHA256 = "07be331e13cc24a2408ed50adb06f1151cdd16754f6d37d7c8c15f894ff5723d"

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

STALE_LEFTOVERS = (
    "$49", "$19", "/ month", "checkout", "one-time", "launch pricing",
    "not yet published", "official distribution package",
)


def _en():
    return EN_PATH.read_text(encoding="utf-8")


def _segment(page, marker):
    start = page.index(marker)
    return page[start:page.index("</section>", start)]


# ---- 1: section structure and order ----

def test_en_core_sections_present_in_order():
    en = _en()
    for marker in SECTION_MARKERS:
        assert marker in en, f"EN missing section: {marker}"
    positions = [en.index(m) for m in SECTION_MARKERS]
    assert positions == sorted(positions), list(zip(SECTION_MARKERS, positions))


# ---- 2: navigation and primary CTAs ----

def test_en_nav_and_primary_ctas():
    en = _en()
    nav = en[en.index("<nav"):en.index("</nav>")]
    assert 'href="#how"' in nav
    assert 'href="#demo-walkthrough"' in nav
    assert 'href="#pricing"' in nav
    assert 'class="nav-buy" href="#acquire"' in nav
    assert 'href="#acquire">START USING TANUQ' in en
    assert 'id="get" href="#acquire"' in en
    assert "<form" not in en.lower() and "<input" not in en.lower()


# ---- 3: pricing truth ----

def test_en_pricing_truth_free():
    en = _en()
    pricing = _segment(en, 'id="pricing"')
    assert "FREE" in pricing
    assert "TANUQ is free to use" in en
    assert "Future pricing has not been decided" in en


# ---- 4: no fake purchase / stale sales language ----

def test_en_no_fake_purchase_language():
    en = _en()
    for label in FAKE_PURCHASE_LABELS:
        assert label not in en, f"fake purchase label present: {label}"
    low = en.lower()
    for leftover in STALE_LEFTOVERS:
        assert leftover not in low, f"stale sales copy present: {leftover}"
    anchor_texts = re.findall(r"<a[^>]*>([^<]*)</a>", en)
    for text in anchor_texts:
        up = text.upper()
        assert not any(w in up for w in ("BUY", "PURCHASE", "SATIN")), text


# ---- 5: recorded proof values ----

def test_en_proof_values_present():
    en = _en()
    for marker in PROOF_VALUES:
        assert marker in en, f"proof value missing: {marker}"


# ---- 6: integration-claim limits ----

def test_en_integration_claims_limited():
    en = _en()
    assert "official Claude Code adapter" in en
    assert "not yet validated" in en


# ---- 7: feedback channel honesty ----

def test_en_feedback_channel_honest():
    en = _en()
    feedback = _segment(en, 'id="feedback"')
    assert "Tried TANUQ? Tell us what happened." in feedback
    assert "Send your experience directly to the TANUQ team" in feedback
    assert en.count("mailto:feedback@tanuq.net") == 1
    assert feedback.count("mailto:feedback@tanuq.net") == 1
    assert "subject=TANUQ%20Feedback" in feedback
    assert "body=" in feedback and "%0A" in feedback
    assert "SEND FEEDBACK" in feedback
    assert "no tracking" in feedback and "no analytics" in feedback


# ---- 8: footer honest limits ----

def test_en_footer_honest_limits():
    en = _en().lower()
    assert "tamper-evident" in en
    assert "no operating-system-level protection" in en
    assert "no network enforcement" in en


# ---- 9: walkthrough asset wiring ----

def test_en_walkthrough_asset_wired():
    en = _en()
    assert 'id="demo-root"' in en
    assert 'data-fixture="demo_fixtures.json"' in en
    assert '<script src="demo.js" defer>' in en


# ---- 10: download block — URLs and hash (checks 1, 2) ----

def test_en_download_urls_bound_to_real_anchors():
    en = _en()
    assert en.count(EXE_URL) == 1, "installer URL missing/duplicated"
    assert en.count(SUMS_URL) == 1, "checksum URL missing/duplicated"
    seg = _segment(en, 'id="try"')
    assert f'<a class="btn btn-primary" href="{EXE_URL}">' in seg, \
        "installer link is not a real <a href> to the verified URL"
    assert f'<a href="{SUMS_URL}">' in seg, \
        "checksum link is not a real <a href> to the verified URL"


def test_en_download_sha256_exact_match():
    en = _en()
    assert en.count(SHA256) == 1, "expected SHA-256 missing/duplicated"
    seg = _segment(en, 'id="try"')
    assert f"<code>{SHA256}</code>" in seg, \
        "expected SHA-256 not shown verbatim in the install section"


# ---- 11: download block — existing classes only (check 3) ----

def test_en_download_block_uses_existing_classes():
    seg = _segment(_en(), 'id="try"')
    assert 'class="btn btn-primary"' in seg
    assert 'class="small"' in seg
    assert "<style" not in seg
    assert "style=" not in seg


# ---- 12: download block — disclosures (check 4) ----

def test_en_download_disclosures():
    seg = _segment(_en(), 'id="try"')
    low = seg.lower()
    assert "windows 10/11 x64" in low
    assert "per-user install" in low
    assert "no admin" in low
    assert "offline after install" in low
    assert "no auto-update" in low
    assert "unsigned" in low
    assert "smartscreen" in low
    assert "defender" in low
    assert "clean windows acceptance: not tested" in low
    assert "developer machine" in low


# ---- 13: FAQ explains installer download and install flow (check 5) ----

def test_en_faq_install_flow():
    en = _en()
    faq = _segment(en, 'id="faq"')
    assert "<summary>How do I install TANUQ?</summary>" in faq
    assert "Python 3.12+ is required" in faq
    assert '<a href="#try">Install</a>' in faq
    assert "Windows installer download (v0.6.0)" in faq
    # the local-install flow in #try stays reachable and explained
    try_seg = _segment(en, 'id="try"')
    assert "pip install -e ." in try_seg
    assert "tanuq init" in try_seg and "tanuq ui" in try_seg


# ---- 14: stale claim absent (check 6) ----

def test_en_stale_not_published_claim_absent():
    low = _en().lower()
    assert "not yet published" not in low
    assert "official distribution package" not in low
