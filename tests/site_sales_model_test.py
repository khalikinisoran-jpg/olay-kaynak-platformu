"""Sales-model contract for the public site (product-led / self-serve).

Contract under test:
  Site → Ürünü anla → Değerini gör → Güven → Fiyat → Satın Al → Kur → Kullan

Guards:
- purchase CTA is the primary path (no demo-request / demo-drive CTA)
- pricing block: single plan TANUQ PRO, $49 / ay, "Kur. Bağla. Yönet."
- GitHub is OUT of the sales path (hero/nav/pricing/purchase)
- no build-vs-buy math and no unproven security claims
- FAQ covers the required pre-purchase questions with real content
- interactive-demo evidence (fixture + walkthrough) is preserved
- no fake checkout/form is introduced

Read-only static-content test (index.html + fixture file existence).
No core files, no demo fixture content, no new dependencies.
"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"


def _html():
    return (SITE / "index.html").read_text(encoding="utf-8")


def _segment(html, start_marker, end_marker=None):
    start = html.index(start_marker)
    if end_marker is None:
        end = html.index("</section>", start)
    else:
        end = html.index(end_marker, start)
    return html[start:end]


def _hero(html):
    return _segment(html, '<section class="hero">')


def _nav(html):
    return html[html.index("<nav"):html.index("</nav>")]


def _cta_final(html):
    return _segment(html, '<section class="section cta-final">')


def _github_anchor_hrefs(text):
    return [
        m.group(1)
        for m in re.finditer(r'<a\b[^>]*?href\s*=\s*"([^"]+)"', text, re.I)
        if "github.com" in m.group(1).lower()
    ]


# ---- pricing ----

def test_pricing_block_single_plan_and_price():
    html = _html()
    pricing = _segment(html, 'id="pricing"')
    assert "TANUQ PRO" in pricing
    assert "$49" in pricing
    assert "/ ay" in pricing
    assert "Kur. Bağla. Yönet." in pricing
    assert "EDİNİMİ BAŞLAT" in pricing
    # commercial status is stated honestly (no checkout / license claims)
    assert "lansman öncesi" in pricing
    assert "açılmamıştır" in pricing
    # no completed-packaging claim without a real subscription system
    assert "tek plan" not in html.lower()
    assert "tek paket" not in html.lower()
    # single plan only: no invented tiers
    for tier in ("Free", "Enterprise", "Team plan", "Business"):
        assert tier not in pricing


def test_pricing_checkout_is_honest():
    html = _html()
    pricing = _segment(html, 'id="pricing"')
    assert "ödeme ve lisanslama" in pricing.lower()
    assert "<form" not in html and "<input" not in html.lower()
    # no unproven "buy now" claim while no payment flow exists
    assert "TANUQ'YU AL" not in html
    assert "satın al" not in html.lower()


# ---- purchase CTAs ----

def test_primary_cta_starts_acquisition_not_fake_checkout():
    html = _html()
    hero = _hero(html)
    nav = _nav(html)
    final = _cta_final(html)
    # every primary CTA starts the acquisition flow at the price block
    assert 'href="#pricing">EDİNİMİ BAŞLAT' in hero
    assert 'class="nav-buy" href="#pricing"' in nav
    assert 'href="#pricing">EDİNİMİ BAŞLAT' in final
    # the buy anchor exists for a future real checkout integration
    assert 'id="buy"' in html
    assert 'id="buy" href="#acquire"' in html
    # acquire + pricing anchors exist for the self-serve flow
    assert 'id="acquire"' in html and 'id="pricing"' in html


def test_no_demo_cta_and_no_demo_request_section():
    html = _html()
    assert 'id="demo"' not in html
    assert "DEMO TALEBİ" not in html
    assert "DEMO TALEP" not in html
    anchor_texts = re.findall(r"<a[^>]*>([^<]*)</a>", html)
    assert not [t for t in anchor_texts if "DEMO" in t.upper()], anchor_texts


# ---- GitHub out of the sales path ----

def test_github_is_out_of_sales_path():
    html = _html()
    sales_path = "\n".join((
        _nav(html),
        _hero(html),
        _segment(html, 'id="pricing"'),
        _segment(html, 'id="acquire"'),
        _segment(html, 'id="faq"'),
        _cta_final(html),
    ))
    assert _github_anchor_hrefs(sales_path) == []
    assert "github.com" not in sales_path.lower()
    # owner decision (site V2): zero GitHub anywhere on the page
    assert _github_anchor_hrefs(html) == []
    assert "github" not in html.lower()
    assert "git clone" not in html


# ---- forbidden content ----

def test_no_build_vs_buy_claims():
    html = _html().lower()
    for phrase in (
        "build vs buy",
        "tasarruf",
        "daha ucuz",
        "daha ucuzuz",
        "kendiniz geliştirm",
        "kendi geliştirme",
        "saat sürer",
        "token tasarruf",
    ):
        assert phrase not in html, f"build-vs-buy style claim present: {phrase}"


def test_no_unproven_security_claims():
    html = _html().lower()
    for phrase in (
        "100% secure",
        "%100 güven",
        "unhackable",
        "zero risk",
        "industry leading",
        "en güvenli",
        "kesin güvenlik",
        "garantili güvenlik",
    ):
        assert phrase not in html, f"unproven claim present: {phrase}"


# ---- narrative sections ----

def test_features_section_lists_verified_capabilities():
    html = _html()
    features = _segment(html, 'id="features"')
    for capability in (
        "DETERMINISTIC RISK",
        "POLICY BINDING",
        "AUTHORIZATION",
        "FINGERPRINT-BOUND",
        "SINGLE-USE",
        "BOUNDED ATTEMPTS",
        "CONTROLLED EXECUTION",
        "VERIFICATION",
        "TAMPER-EVIDENT EVIDENCE",
        "HASH-CHAIN LINEAGE",
    ):
        assert capability in features, capability


def test_statement_differentiation_present():
    html = _html()
    assert "Yapay zekâ değişebilir" in html
    assert "Yönetim ve kanıt katmanı değişmemeli" in html
    assert "Agent intelligence is replaceable. Governance state is not." in html


def test_trust_section_uses_real_mechanisms():
    html = _html()
    trust = _segment(html, 'id="trust"')
    for mechanism in ("Değişiklik kimliği", "Authorization", "Fingerprint",
                      "Verification", "Evidence", "Fail-closed"):
        assert mechanism in trust, mechanism
    assert "100%" not in trust and "unhackable" not in trust.lower()


def test_acquire_flow_has_five_steps():
    html = _html()
    acquire = _segment(html, 'id="acquire"')
    assert acquire.count('<span class="step-num">') == 5
    assert "Edinim durumunu gör" in acquire
    assert "Agent'ını bağla" in acquire
    assert "ödeme altyapısı bu aşamada bağlı değildir" in acquire
    assert 'href="#try"' in acquire  # install commands stay technical, after purchase


def test_section_order_matches_sales_flow():
    """Site → Ürünü anla → Kanıt → Ürün → Fiyat → Edinim → Teknik → SSS."""
    html = _html()
    markers = [
        'class="section problem"',
        'id="how"',
        'id="demo-walkthrough"',
        'class="section product"',
        'id="pricing"',
        'id="acquire"',
        'id="try"',
        'id="faq"',
        'class="section cta-final"',
    ]
    positions = [html.index(m) for m in markers]
    assert positions == sorted(positions), list(zip(markers, positions))
    # no GitHub clone commands anywhere (owner decision: site V2)
    assert "git clone" not in html


# ---- FAQ ----

def test_faq_covers_required_questions():
    html = _html()
    faq = _segment(html, 'id="faq"')
    required = (
        "TANUQ nedir?",
        "Hangi agent'larla çalışır?",
        "Agent değişirse TANUQ ne olur?",
        "TANUQ agent'ın yerine mi geçer?",
        "Approval nasıl çalışır?",
        "Risk nasıl belirlenir?",
        "Verification ne yapar?",
        "Evidence neden önemlidir?",
        "Kurulum nasıl yapılır?",
        "Nasıl edinilir?",
        "TANUQ'nun sınırları nelerdir?",
    )
    for question in required:
        assert question in faq, f"FAQ missing question: {question}"
    assert faq.count("<summary>") == len(required)


# ---- preserved real evidence ----

def test_interactive_walkthrough_evidence_preserved():
    html = _html()
    walkthrough = _segment(html, 'id="demo-walkthrough"')
    assert 'data-fixture="demo_fixtures.json"' in walkthrough
    assert 'src="demo.js"' in html
    fixture = json.loads((SITE / "demo_fixtures.json").read_text(encoding="utf-8"))
    assert fixture["source"]["type"] == "recorded_real_run"
    assert fixture["scenario"]["risk"] == "HIGH"


# ---- Hata #1: never an error state in public output ----

def test_walkthrough_never_shows_error_state():
    html = _html()
    js = (SITE / "demo.js").read_text(encoding="utf-8")
    for text in ("Walkthrough unavailable", "Failed to fetch", "Could not load", "Serve site"):
        assert text not in html, f"error text in index.html: {text}"
        assert text not in js, f"error text in demo.js: {text}"
    # graceful degradation: a real recorded-run summary ships in the HTML
    for marker in ("recorded_real_run", "06d0ba48d949", "864c6050",
                   "chain VALID", "events 11", "deploy_demo.py"):
        assert marker in html, f"static recorded summary missing: {marker}"
    # demo.js keeps that static summary visible on any fixture failure
    assert "staticHTML" in js and "restoreStatic" in js


# ---- Hata #6/#7: no unverified breadth claims ----

def test_no_unverified_integration_breadth_claims():
    html = _html().lower()
    for phrase in (
        "tüm agent",
        "her ajanla",
        "her agentla",
        "tüm ai agent",
        "her sağlayıcıyla",
        "tüm sağlayıcı",
        "enterprise ready",
        "production proven",
        "zero trust",
        "compliance",
        "sertifika",
        "çalışabilecek bağımsız",
    ):
        assert phrase not in html, f"unverified breadth claim: {phrase}"
    # the verified integrations are stated explicitly and are limited
    assert "resmi adaptör" in html
    assert "stdin-json" in html
    assert "henüz doğrulanmamıştır" in html
