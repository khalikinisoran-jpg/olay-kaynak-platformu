"""G-04 contract: /try/* scripts are repo-internal, not downloads.

The public surface must not represent the TRY scripts as
standalone-downloadable: the landing page links them nowhere (it shows
the repo-internal commands only), the deploy doc must not claim they
are downloadable, and the scripts themselves must state the
repo-internal requirement. Read-only static-content test.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"


def _read(rel):
    return (SITE / rel).read_text(encoding="utf-8")


def test_landing_does_not_link_try_scripts_as_downloads():
    html = _read("index.html")
    assert 'href="try/' not in html
    assert 'href="try_tanuq' not in html
    # the repo-internal usage commands must stay
    assert "git clone" in html
    assert "try_tanuq.ps1" in html and "try_tanuq.sh" in html


def test_deploy_doc_does_not_claim_downloadable_scripts():
    deploy = _read("DEPLOY.md").lower()
    assert "downloadable" not in deploy
    assert "download links" not in deploy
    assert "repo-internal" in deploy
    assert "not standalone downloads" in deploy
    # the supported repo-internal path stays documented
    assert "pip install -e ." in deploy
    assert "clone the" in deploy


def test_scripts_state_repo_internal_requirement():
    for rel in ("try/try_tanuq.ps1", "try/try_tanuq.sh"):
        s = _read(rel).lower()
        assert "repo-internal" in s, f"missing repo-internal note: {rel}"
        assert "not a" in s and "standalone download" in s
        assert "pip install -e ." in s
