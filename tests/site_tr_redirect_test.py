"""FAZ 3C — /tr/ static redirect page contract (B-min).

New module (G1): no existing test module is modified.

Owner decision: the Turkish page is NOT offered to users; `/tr/` keeps a
host-independent static redirect page to the English default (`/`).

Covers:
1. `site/tr/index.html` stays in the repo as a minimal redirect page:
   - `meta http-equiv="refresh"` -> `../` (no server configuration)
   - `canonical` -> https://tanuq.net/
   - a visible link to the English home page (works without JavaScript)
   - valid HTML5 skeleton with `lang="en"`
   - no `<script>` dependency
2. the EN default (`site/index.html`) nav carries NO `/tr/` link.
3. `site/DEPLOY.md` documents the new behaviour.

Read-only static-content test: no deploy, no hosting change.
"""
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SITE = REPO / "site"
EN_PATH = SITE / "index.html"
TR_PATH = SITE / "tr" / "index.html"
DEPLOY_PATH = SITE / "DEPLOY.md"

CANONICAL = "https://tanuq.net/"
REFRESH = '<meta http-equiv="refresh" content="0;url=../">'
VISIBLE_LINK = '<a href="../">'


def _en():
    return EN_PATH.read_text(encoding="utf-8")


def _tr():
    return TR_PATH.read_text(encoding="utf-8")


# ---- 1: redirect page stays in the repo ----

def test_redirect_page_exists_in_repo():
    assert TR_PATH.exists(), "site/tr/index.html must stay (redirect page)"


def test_redirect_page_is_static_redirect_to_root():
    page = _tr()
    assert REFRESH in page, "meta refresh to ../ missing"
    assert f'<link rel="canonical" href="{CANONICAL}">' in page
    assert '<html lang="en">' in page
    assert page.lstrip().startswith("<!DOCTYPE html>")
    # no JavaScript dependency, no server-side config needed
    assert "<script" not in page.lower()


def test_redirect_page_has_visible_link_without_js():
    page = _tr()
    assert VISIBLE_LINK in page, "visible link to ../ missing"
    # the link sits in the body, not only in the meta tag
    body = page[page.index("<body"):]
    assert VISIBLE_LINK in body
    # the old Turkish content is gone
    assert "bağımsız yönetim katmanı" not in page
    assert "TANUQ'U KULLAN" not in page


# ---- 2: EN default carries no /tr/ link ----

def test_en_page_has_no_tr_link():
    en = _en()
    nav = en[en.index("<nav"):en.index("</nav>")]
    assert 'href="tr/index.html"' not in nav, "TR link still in EN nav"
    assert "lang-switch" not in nav, "language switcher still in EN nav"
    assert "tr/index.html" not in en, "TR reference still on the EN page"


# ---- 3: deploy doc states the new behaviour ----

def test_deploy_md_documents_redirect_behaviour():
    deploy = DEPLOY_PATH.read_text(encoding="utf-8")
    low = deploy.lower()
    assert "site/tr/" in deploy
    assert "redirect" in low
    assert "meta refresh" in low
    assert "javascript" in low
