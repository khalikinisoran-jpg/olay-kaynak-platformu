"""Free-distribution contract for the public site (TANUQ FREE strategy).

Contract under test:
  Site → Ürünü anla → Kanıt → ÜCRETSİZ (no price/payment) → Kur → Kullan
  + GERİ BİLDİRİM (honest feedback call, no fake form/backend)

Guards:
- FREE model: no $49, no $19, no subscription/checkout/purchase claims
- primary CTA = start using TANUQ (no demo-request, no buy-now CTA)
- GitHub is OUT of the page (hero/nav/pricing/feedback)
- no build-vs-buy math and no unproven security claims
- FAQ covers the required questions with real content (incl. free)
- interactive-demo evidence (fixture + walkthrough) is preserved
- no fake checkout/form/back end is introduced

Read-only static-content test (index.html + fixture file existence).
No core files, no demo fixture content, no new dependencies.
"""
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"


def _html():
    """Sales-flow contract targets the TURKISH surface (site/tr/index.html);
    the English default is covered by tests/site_i18n_test.py."""
    return (SITE / "tr" / "index.html").read_text(encoding="utf-8")


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


# ---- pricing (FREE model) ----

def test_pricing_block_is_free():
    html = _html()
    pricing = _segment(html, 'id="pricing"')
    assert "TANUQ PRO" in pricing
    assert "ÜCRETSİZ" in pricing
    assert "Kur. Bağla. Yönet." in pricing
    assert "TANUQ ücretsizdir" in pricing
    # FREE strategy: no price, no period, no payment language anywhere
    for leftover in ("$49", "$19", "/ ay", "/ month", "lansman öncesi",
                     "açılmamıştır", "abonelik fiyat"):
        assert leftover not in html, f"sales leftover present: {leftover}"
    # no invented tiers (only the free product package)
    for tier in ("Enterprise", "Team plan", "Business"):
        assert tier not in pricing


def test_no_payment_language_left():
    html = _html()
    # no fake checkout machinery, no purchase claims
    assert "<form" not in html and "<input" not in html.lower()
    assert "checkout" not in html.lower()
    for claim in ("TANUQ'YU AL", "SATIN AL", "START ACQUISITION",
                  "EDİNİMİ BAŞLAT", "PURCHASE"):
        assert claim not in html, f"purchase/acquisition claim present: {claim}"
    # free-truth statements exist
    assert "TANUQ ücretsizdir" in html
    assert "hesap yok, ödeme yok" in html


# ---- primary CTAs (free use) ----

def test_primary_cta_starts_using_not_purchase():
    html = _html()
    hero = _hero(html)
    nav = _nav(html)
    final = _cta_final(html)
    # every primary CTA starts the free install/use flow
    assert 'href="#acquire">TANUQ\'U KULLAN' in hero
    assert 'class="nav-buy" href="#acquire"' in nav
    assert 'href="#acquire">TANUQ\'U KULLAN' in final
    # free-flow anchors: get (pricing card) + acquire exist; buy anchor gone
    assert 'id="get" href="#acquire"' in html
    assert 'id="buy"' not in html
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
    assert "TANUQ'u edin (ücretsiz)" in acquire
    assert "hesap yok, ödeme yok, abonelik yok" in acquire
    assert "Agent'ını bağla" in acquire
    assert 'href="#try"' in acquire  # install commands stay reachable


def test_section_order_matches_free_flow():
    """Site → Kanıt → Ürün → ÜCRETSİZ → Edinim/Kur → Teknik → SSS → Geri bildirim."""
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
        'id="feedback"',
        'class="section cta-final"',
    ]
    positions = [html.index(m) for m in markers]
    assert positions == sorted(positions), list(zip(markers, positions))
    # no GitHub clone commands anywhere (owner decision: site V2)
    assert "git clone" not in html


# ---- feedback (free strategy second pillar) ----

def test_feedback_section_is_honest_without_fake_backend():
    html = _html()
    feedback = _segment(html, 'id="feedback"')
    assert "GERİ BİLDİRİM" in feedback
    # honest channel statement: no form on the page, no automatic collection
    assert "form yok" in feedback
    assert "otomatik toplamaz" in feedback
    assert "izleme yok" in feedback
    # the signals we want are present as prompts (not a required form)
    for prompt in ("Hangi agent", "Hangi değişikliği", "ZORLANDINIZ",
                   "tekrar çalıştırır"):
        assert prompt in feedback, f"feedback prompt missing: {prompt}"
    # no fake form / fake backend anywhere
    assert "<form" not in html and "<input" not in html.lower()


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
        "TANUQ ücretsiz mi?",
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
    assert 'data-fixture="../demo_fixtures.json"' in walkthrough  # /tr/ subpath
    assert 'src="../demo.js"' in html
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
