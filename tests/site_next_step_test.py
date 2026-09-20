"""End-user V1 next-step bridge tests (G-02 + G-03).

Contract: the first-time user must never hit a dead end.

- The landing "AJANINIZI BAĞLAYIN" card must show the concrete,
  verified starting path (pip install -e . / tanuq init / tanuq ui).
- The landing #demo section must show the same starting path.
- Both TRY demo scripts must print a next-steps block (real product
  entry) after the OVERALL PASS summary, without altering the real
  governed success output.
- No speculative/future capabilities may appear on the landing page.

Read-only static-content tests; no existing test module is modified
(G1: new tests go in NEW modules).
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"

START_COMMANDS = ("pip install -e .", "tanuq init", "tanuq ui")

FORBIDDEN_SPECULATIVE_TERMS = (
    "roadmap",
    "trajectory governance",
    "kaçış tespiti",
    "çoklu-ajan yönetimi",
    "anomali",
    "araştırma aşamasında",
)


def _read(rel):
    return (SITE / rel).read_text(encoding="utf-8")


def _segment(text, start_marker, end_marker):
    start = text.index(start_marker)
    end = text.index(end_marker, start)
    return text[start:end]


def test_landing_connect_card_shows_concrete_starting_commands():
    html = _read("index.html")
    card = _segment(html, "AJANINIZI BAĞLAYIN", "GENEL SÖZLEŞME")
    for cmd in START_COMMANDS:
        assert cmd in card, f"connect card missing starting command: {cmd}"


def test_landing_demo_section_shows_starting_commands():
    html = _read("index.html")
    section = _segment(html, 'id="demo"', 'id="limits"')
    for cmd in START_COMMANDS:
        assert cmd in section, f"#demo section missing starting command: {cmd}"


def test_try_demo_powershell_prints_next_steps_after_success():
    script = _read("try/try_tanuq.ps1")
    tail = script[script.rindex("OVERALL PASS"):]
    for cmd in START_COMMANDS:
        assert cmd in tail, f"ps1 next-steps block missing: {cmd}"


def test_try_demo_bash_prints_next_steps_after_success():
    script = _read("try/try_tanuq.sh")
    tail = script[script.rindex("OVERALL PASS"):]
    for cmd in START_COMMANDS:
        assert cmd in tail, f"bash next-steps block missing: {cmd}"


def test_try_scripts_keep_overall_pass_summary_intact():
    for rel in ("try/try_tanuq.ps1", "try/try_tanuq.sh"):
        s = _read(rel)
        assert "OVERALL PASS" in s
        assert "Governed demo finished: proposal -> risk -> approval ->" in s
        assert "Cleanup" in s or "cleanup" in s


def test_landing_adds_no_speculative_capabilities():
    html = _read("index.html").lower()
    for term in FORBIDDEN_SPECULATIVE_TERMS:
        assert term not in html, f"speculative term on landing: {term}"
