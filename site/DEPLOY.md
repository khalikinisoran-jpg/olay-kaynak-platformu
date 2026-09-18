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
site/try/*             -> /try/*   (downloadable demo scripts)
```

## Domain

1. Point DNS for `tanuq.net` at the hosting provider
   (CNAME or A record per provider instructions).
2. Enable HTTPS (automatic on the providers listed above).
3. Verify `https://tanuq.net` serves `index.html`, `style.css`
   and that the try-script download links resolve.

## Requirements / constraints

- No server-side code, database, or background service is required for V1.
- No user data is collected by the site itself (static pages, no tracking).
- The try scripts run **on the visitor's own machine** and touch only a
  disposable temporary workspace.

## Later gates (out of scope for V1)

- PyPI publication (removes the `git clone` step from onboarding).
- Server-side sandboxed demo (introduces an attack surface — separate
  security review required).
- Analytics (only privacy-preserving, opt-in aggregation).
