"""FAZ 3C — public site download block contract (EN/TR).

New module (G1): no existing test module is modified.

Covers, for both `site/index.html` (EN default) and
`site/tr/index.html` (TR):

1. the two verified public URLs are wired in the `#try` section:
   - https://tanuq.net/downloads/TANUQ-Setup-0.6.0.exe
   - https://tanuq.net/downloads/SHA256SUMS.txt
2. the published SHA-256 is shown for pre-install verification;
3. the honest disclosures in both languages:
   - Windows 10/11 x64, per-user install (no admin), offline after
     install, no auto-update (new version = new download);
   - installer is unsigned / imzasiz -> SmartScreen/Defender warnings
     are expected;
   - clean Windows acceptance: NOT TESTED (developer machine only);
4. EN/TR semantic parity (same URLs, same hash, same disclosure set);
5. the stale "distribution package not yet published" claim is gone
   and the PyPI v0.6.0 statement (owner fact) is present;
6. `site/DEPLOY.md` maps `site/downloads/*` -> `/downloads/*` and does
   NOT present undocumented hosting behaviour (size/MIME/download) as
   fact.

Read-only static-content test: no deploy, no CSS/JS, no core files.

Retired (Owner-approved): the TR / cross-language variants of items 1-5
(6 tests) — the EN guarantees now live in
`tests/site_en_surface_test.py` and `tests/site_en_surface_deep_test.py`;
this module keeps the EN disclosures (item 3) and the DEPLOY.md mapping
(item 6).
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"
EN_PATH = SITE / "index.html"
TR_PATH = SITE / "tr" / "index.html"
DEPLOY_PATH = SITE / "DEPLOY.md"

EXE_URL = "https://tanuq.net/downloads/TANUQ-Setup-0.6.0.exe"
SUMS_URL = "https://tanuq.net/downloads/SHA256SUMS.txt"
SHA256 = "07be331e13cc24a2408ed50adb06f1151cdd16754f6d37d7c8c15f894ff5723d"


def _en():
    return EN_PATH.read_text(encoding="utf-8")


def _tr():
    return TR_PATH.read_text(encoding="utf-8")


def _segment(page, marker):
    start = page.index(marker)
    return page[start:page.index("</section>", start)]


# ---- 3: honest disclosures (per language) ----

def test_honest_disclosures_english():
    seg = _segment(_en(), 'id="try"')
    low = seg.lower()
    assert "windows 10/11 x64" in low
    assert "no admin" in low
    assert "offline" in low
    assert "no auto-update" in low
    assert "unsigned" in low
    assert "smartscreen" in low
    assert "defender" in low
    assert "clean windows acceptance: not tested" in low
    assert "developer machine" in low


# ---- 6: DEPLOY.md documents the mapping without inventing facts ----

def test_deploy_md_documents_downloads_mapping():
    deploy = DEPLOY_PATH.read_text(encoding="utf-8")
    low = deploy.lower()
    assert "site/downloads/*" in deploy
    assert "/downloads/*" in deploy
    # undocumented hosting behaviour must stay marked as unknown
    assert "not documented" in low
    assert "unknown" in low
    # existing repo-internal contract untouched (G-04)
    assert "repo-internal" in low
    assert "not standalone downloads" in low
