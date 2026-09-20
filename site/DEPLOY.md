# Deploying tanuq.net (V1)

The public product surface is a **static site** (`site/index.html`,
`site/style.css`) plus a **local try script** (`site/try/`). No server-side
components, no accounts, no tracking.

## What to deploy

Upload the contents of `site/` to any static hosting provider
(GitHub Pages, Cloudflare Pages, Netlify, or a simple web server):

```
site/index.html        -> /
site/style.css         -> /style.css
site/try/*             -> /try/*   (optional; NOT linked from the page —
                                   scripts are repo-internal, see below)
```

## Domain

1. Point DNS for `tanuq.net` at the hosting provider
   (CNAME or A record per provider instructions).
2. Enable HTTPS (automatic on the providers listed above).
3. Verify `https://tanuq.net` serves `index.html` and `style.css`
   (the try scripts are repo-internal and intentionally not linked
   from the page).

## Requirements / constraints

- No server-side code, database, or background service is required for V1.
- No user data is collected by the site itself (static pages, no tracking).
- The try scripts run **on the visitor's own machine** and touch only a
  disposable temporary workspace.

## Try scripts are repo-internal (not standalone downloads)

`site/try/try_tanuq.ps1` and `site/try/try_tanuq.sh` resolve the
repository root relative to their own location and require the tanuq
package installed from that repository (`pip install -e .`). They are
**not** standalone downloads: the landing page links them nowhere, and
a copy fetched from `/try/*` and run elsewhere fails closed. The only
supported path is the one documented on the landing page: clone the
repository, run `pip install -e .`, then run the script from inside
the repository.

## Later gates (out of scope for V1)

- PyPI publication (removes the `git clone` step from onboarding).
- Server-side sandboxed demo (introduces an attack surface — separate
  security review required).
- Analytics (only privacy-preserving, opt-in aggregation).
