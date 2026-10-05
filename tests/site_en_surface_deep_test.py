"""TANUQ FREE — EN surface DEEP contract (gap-closing module).

New module (G1): no existing test module is modified; product files are
read-only inputs.

Context: after the B-min owner decision the English default
(`site/index.html`) is the only published content surface. This module
closes the coverage gaps left by the legacy TR-surface modules (pending
an Owner decision) and asserts ONLY content that actually exists on the
EN page today.

Covers (gap list 1-14):
 1. strategic positioning + problem/customer language,
 2. benefit (VALUE) and FEATURES cards,
 3. trust mechanisms + honest claim limits (no unsupported claim),
 4. five-step acquire/start flow,
 5. FAQ coverage: all 12 <summary> headings,
 6. five feedback prompts + honest single mailto (no tracking claims),
 7. "Who it's for" personas + benefit texts,
 8. EN logo + favicon references (root-relative assets),
 9. APPROVAL_REQUIRED usage in proof/product areas,
10. PyPI 0.6.0 distribution narrative,
11. no roadmap / anomaly capabilities presented as existing,
12. no DEMO CTA / demo-request surface,
13. no TANUK misspelling,
14. no fake contact form.

Read-only static-content test: no deploy, no hosting change.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"
EN_PATH = SITE / "index.html"


def _en():
    return EN_PATH.read_text(encoding="utf-8")


def _segment(page, marker):
    start = page.index(marker)
    return page[start:page.index("</section>", start)]


# ---- 1: strategic positioning and problem language ----

def test_en_strategic_positioning_present():
    en = _en()
    hero = _segment(en, '<section class="hero">')
    assert "<h1>An independent governance layer<br>" in hero
    assert "for your AI coding agent" in hero
    statement = _segment(en, 'class="section statement"')
    assert "Models change." in statement
    assert "The governance and evidence layer must not." in statement
    assert ("Agent intelligence is replaceable. "
            "Governance state is not.") in statement
    final = _segment(en, 'class="section cta-final"')
    assert "Stay in control. Get started with TANUQ." in final


def test_en_problem_section_speaks_customer_language():
    problem = _segment(_en(), 'class="section problem"')
    assert "<h2>When an AI agent changes code, who has the final say?</h2>" \
        in problem
    assert "who decides which changes need control?" in problem
    assert "rollback is costly and slow" in problem
    assert "independent governance layer" in problem


# ---- 1b: hero lede (bound to the hero section) ----

def test_en_hero_lede_present_in_hero():
    en = _en()
    hero_start = en.index('<section class="hero">')
    hero_end = en.index("</section>", hero_start)
    lede_tag = '<p class="lede">'
    # the hero lede tag exists exactly once on the page (section-lede is a
    # different class and must not satisfy this check)
    assert en.count(lede_tag) == 1, "hero <p class=\"lede\"> count drifted"
    lede_pos = en.index(lede_tag)
    assert hero_start < lede_pos < hero_end, "hero lede not inside <section hero>"
    # the real lede sentence, verified inside the hero segment only
    hero = en[hero_start:hero_end]
    lede_start = hero.index(lede_tag)
    lede_end = hero.index("</p>", lede_start)
    lede = hero[lede_start:lede_end]
    assert "The agent proposes. TANUQ assesses risk, requests your approval" \
        " when required, executes, verifies, and provides evidence of what" \
        " happened." in lede
    assert "TANUQ is free to use." in lede
    # uniqueness: the sentence must not exist elsewhere (no false pass)
    assert en.count("The agent proposes. TANUQ assesses risk") == 1
    assert lede.startswith('<p class="lede">The agent proposes.')


# ---- 1c: #how six-step flow, content and order ----

def test_en_how_section_six_steps_in_order():
    en = _en()
    assert en.count('<section id="how"') == 1, "how section missing/duplicated"
    how = _segment(en, 'id="how"')
    assert "<h2>Six steps.</h2>" in how
    # the flow line exactly as in the source
    assert ("Propose \u2192 Risk \u2192 Approval \u2192 Execute \u2192 Verify "
            "\u2192 Evidence. Every step is visible; authority never moves to "
            "the next step on its own.") in how
    # exactly six step blocks
    assert how.count('<div class="step">') == 6
    # number + title pairs, in source order, each bound to its step number
    pairs = (
        ("1", "Proposal"),
        ("2", "Assessment"),
        ("3", "Approval"),
        ("4", "Execution"),
        ("5", "Verification"),
        ("6", "Evidence"),
    )
    keys = [
        f'<span class="step-num">{n}</span><strong>{title}</strong>'
        for n, title in pairs
    ]
    positions = [how.index(key) for key in keys]
    assert positions == sorted(positions), \
        f"step order drifted: {list(zip([t for _, t in pairs], positions))}"
    # real per-step text from the source (not just titles)
    step_texts = (
        "it sends a change proposal to TANUQ",
        "acceptable changes can be applied, risky changes wait for your "
        "approval",
        "Nothing is applied without your approval",
        "Approved changes are applied atomically",
        "Compilation and tests run after the apply",
        "Later modifications to the record can be detected",
    )
    for text in step_texts:
        assert text in how, f"how step text missing: {text}"


# ---- 2: benefit (VALUE) and FEATURES cards ----

def test_en_value_cards_present():
    value = _segment(_en(), 'class="section value"')
    assert value.count('<div class="card">') == 4
    for title in ("CONTROL", "VISIBILITY", "VERIFICATION", "EVIDENCE"):
        assert f"<h3>{title}</h3>" in value, f"VALUE card missing: {title}"
    assert "nothing is applied without your approval" in value
    assert "which content diff" in value
    assert "the outcome is verified" in value
    assert "Later modifications to the record can be detected" in value


def test_en_features_cards_present():
    features = _segment(_en(), 'id="features"')
    assert features.count('<div class="card">') == 10
    for title in ("DETERMINISTIC RISK", "POLICY BINDING", "AUTHORIZATION",
                  "FINGERPRINT-BOUND", "SINGLE-USE", "BOUNDED ATTEMPTS",
                  "CONTROLLED EXECUTION", "VERIFICATION",
                  "TAMPER-EVIDENT EVIDENCE", "HASH-CHAIN LINEAGE"):
        assert f"<h3>{title}</h3>" in features, f"FEATURES card missing: {title}"
    assert "uncertain (UNKNOWN) outcomes are never treated as success" \
        in features


# ---- 3: trust mechanisms and honest claim limits ----

def test_en_trust_mechanisms_and_limits():
    trust = _segment(_en(), 'id="trust"')
    assert "<h2>Trust comes from mechanisms.</h2>" in trust
    assert "Not a marketing claim" in trust
    for mechanism in ("Change identity", "Authorization", "Fingerprint",
                      "Verification", "Evidence &amp; hash chain",
                      "Fail-closed"):
        assert f"<strong>{mechanism}</strong>" in trust, mechanism
    # limits: the page must not claim more than the product does
    assert "100%" not in trust
    assert "unhackable" not in trust.lower()
    assert "guaranteed" not in trust.lower()


# ---- 4: five-step acquire flow ----

def test_en_acquire_flow_has_five_steps():
    acquire = _segment(_en(), 'id="acquire"')
    assert acquire.count('<span class="step-num">') == 5
    for title in ("Get TANUQ (free)", "Install", "Connect your agent",
                  "Manage", "Use"):
        assert f"<strong>{title}</strong>" in acquire, title
    assert 'href="#try"' in acquire  # install commands stay reachable
    assert '<a class="btn btn-secondary" href="#try">INSTALL COMMANDS</a>' \
        in acquire


# ---- 5: FAQ coverage (all 12 summaries on the real page) ----

def test_en_faq_has_all_twelve_questions():
    faq = _segment(_en(), 'id="faq"')
    summaries = faq.count("<summary>")
    assert summaries == 12, f"FAQ summary count changed: {summaries}"
    expected = (
        "What is TANUQ?",
        "Which agents does TANUQ support?",
        "What happens when I change agents?",
        "Does TANUQ replace my coding agent?",
        "How does approval work?",
        "How is risk determined?",
        "What does verification do?",
        "Why does evidence matter?",
        "How do I install TANUQ?",
        "Is TANUQ free?",
        "How can I get TANUQ?",
        "What are TANUQ's limits?",
    )
    for question in expected:
        assert f"<summary>{question}</summary>" in faq, question
    # honest answers preserved
    assert "Future pricing has not been decided yet." in faq
    assert "it does not sandbox your agent" in faq
    assert "Other agent integrations are not yet validated." in faq


# ---- 6: feedback prompts + honest single mailto ----

def test_en_feedback_prompts_and_honest_mailto():
    en = _en()
    feedback = _segment(en, 'id="feedback"')
    assert feedback.count('<div class="card">') == 5
    for prompt in ("WHAT WERE YOU PROTECTING?", "WHICH AGENT?",
                   "WHAT WORKED?", "WHAT WAS HARD?",
                   "WOULD YOU USE IT AGAIN?"):
        assert f"<h3>{prompt}</h3>" in feedback, prompt
    # honest mailto behaviour: exactly one real channel, encoded payload
    assert en.count("mailto:feedback@tanuq.net") == 1
    assert feedback.count("mailto:feedback@tanuq.net") == 1
    assert "subject=TANUQ%20Feedback" in feedback
    assert "body=" in feedback and "%0A" in feedback
    assert "SEND FEEDBACK" in feedback
    # no tracking claimed as present (and none wired)
    assert "Nothing on this page collects data automatically." in feedback
    assert "no tracking, no accounts, no analytics" in feedback
    low = en.lower()
    assert "google-analytics" not in low
    assert "gtag" not in low


# ---- 7: who it's for ----

def test_en_who_it_is_for_personas():
    who = _segment(_en(), 'class="section who')
    assert who.count('<div class="persona">') == 4
    expected = (
        ("Teams using AI coding agents", "independent control layer"),
        ("Platform Engineering", "independent governance layer"),
        ("Security / DevSecOps", "policy framework"),
        ("AI Infrastructure", "vendor-blind governance layer"),
    )
    for persona, benefit in expected:
        assert f"<strong>{persona}</strong>" in who, persona
        assert benefit in who, benefit


# ---- 8: EN logo and favicon references ----

def test_en_logo_and_favicon_references():
    en = _en()
    assert 'href="assets/tanuq-favicon.png"' in en
    assert 'src="assets/tanuq-logo-header-sm.png"' in en
    # EN page uses root-relative assets (no ../ subpath leakage)
    assert 'href="../' not in en
    assert 'src="../' not in en


# ---- 9: APPROVAL_REQUIRED in proof/product areas ----

def test_en_approval_required_used_in_proof_areas():
    en = _en()
    hero = _segment(en, '<section class="hero">')
    assert "state: APPROVAL_REQUIRED · risk: HIGH" in hero
    product = _segment(en, 'class="section product"')
    assert "state: APPROVAL_REQUIRED · risk: HIGH" in product
    walkthrough = _segment(en, 'id="demo-walkthrough"')
    assert ">APPROVAL REQUIRED<" in walkthrough  # badge form
    assert en.count("APPROVAL_REQUIRED") == 2  # hero + product, no drift


# ---- 9b: hero terminal proof block (real recorded run) ----

def test_en_hero_term_proof_block_contains_real_run():
    en = _en()
    pre_tag = '<pre class="term-proof">'
    # exactly one such block on the whole page (hero-only)
    assert en.count(pre_tag) == 1, "term-proof block missing/duplicated"
    hero_start = en.index('<section class="hero">')
    hero_end = en.index("</section>", hero_start)
    hero = en[hero_start:hero_end]
    assert hero.count(pre_tag) == 1, "term-proof block not bound to hero"
    # extract the block itself: assertions run on its content only,
    # so no other page text can satisfy them
    start = hero.index(pre_tag) + len(pre_tag)
    end = hero.index("</pre>", start)
    block = hero[start:end]
    assert block.strip(), "term-proof block is empty"
    lines = [line.strip() for line in block.splitlines()]
    # the recorded run opens with the propose line
    assert lines[0].startswith("propose"), f"unexpected first line: {lines[0]!r}"
    # whitespace-tolerant content checks (real spacing/indent from source)
    flat = " ".join(block.split())
    assert "propose → state: APPROVAL_REQUIRED · risk: HIGH" in flat
    assert "execute → terminal state: VERIFIED" in flat
    assert "Apply success: True" in flat
    assert "Verification passed: True" in flat


# ---- 10: PyPI 0.6.0 distribution narrative ----

def test_en_pypi_distribution_narrative():
    try_seg = _segment(_en(), 'id="try"')
    assert "TANUQ is distributed as source on this page" in try_seg
    assert "as version 0.6.0 on PyPI" in try_seg
    assert "as the Windows installer below" in try_seg


# ---- 11: no roadmap / anomaly capability presented ----

def test_en_no_roadmap_or_anomaly_claims():
    low = _en().lower()
    for phrase in ("roadmap", "anomaly", "coming soon", "will be added"):
        assert phrase not in low, f"unreleased capability hinted: {phrase}"


# ---- 12: no DEMO CTA / demo request ----

def test_en_no_demo_cta():
    en = _en()
    hero = _segment(en, '<section class="hero">')
    assert "DEMO" not in hero.upper()
    low = en.lower()
    assert 'id="demo"' not in en  # only id="demo-walkthrough" exists
    for phrase in ("request a demo", "book a demo", "demo request",
                   "try the demo"):
        assert phrase not in low, f"demo CTA present: {phrase}"


# ---- 13: no TANUK misspelling ----

def test_en_no_tanuk_misspelling():
    en = _en()
    assert "TANUK" not in en
    assert "TANUQ" in en


# ---- 14: no fake contact form ----

def test_en_no_contact_form():
    low = _en().lower()
    assert "<form" not in low
    assert "<input" not in low
    assert "<textarea" not in low
