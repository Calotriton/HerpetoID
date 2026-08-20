# HerpetoID website

The public site at <https://calotriton.github.io/HerpetoID/>. Jekyll, published by GitHub Pages via
[`.github/workflows/pages.yml`](../.github/workflows/pages.yml). Only this folder is published — the
Python package, the tests and the internal notes in `docs/` are never part of the site.

---

## The design system — read this before adding anything

The site is a **design system, not a pile of pages**. Everything on it is assembled from a small set
of components, and every component takes its colours, radii and shadows from tokens. That is what
keeps a page added a year from now looking like it belongs.

**The live inventory is [`/style-guide/`](style-guide.html)** — open it in a browser. If what you
need is on that page, compose it. If it is not, add the component to `assets/css/main.css` *and*
show it on the style guide, then use it.

### The identity

A **field instrument**: graphite surfaces, one signal-amber accent, hairline rules, a faint
graph-paper grid behind the hero. Deliberately *not* the application's teal — the app and the site
are allowed to be different objects.

**Monospace is for machine text only** — labels, metadata, counters, file names, code,
measurements. Prose is always the system sans. If you are unsure, ask whether a program produced
the text.

**No web fonts.** The site promises visitors that nothing they do here reaches a third party, and
loading a font from Google would quietly break that promise on every page view. System stacks only.

### The four rules

1. **No colour literal outside the token block.** Everything above `=== END OF TOKENS ===` in
   `main.css` owns the palette; everything below asks for it by name with `var(--token)`. That
   includes inline SVG in pages — diagrams theme themselves through the same tokens.
2. **No `style="…"` attributes.** An inline style is a component nobody wrote down. Use a component,
   or one of the short list of utilities in section 5 of `main.css`.
3. **Both themes, always.** Dark values live twice — under `prefers-color-scheme` *and* under
   `[data-theme="dark"]`, because the site supports both "follow the system" and the header toggle.
   Change one and you must change the other. Check your work with the toggle.
4. **Reachable and responsive.** Keyboard-navigable with a visible focus ring, decorative marks
   `aria-hidden`, works at 360px wide, and anything wide (tables, code) scrolls inside its own
   container rather than the page.

These are enforced, not just documented: **`pytest tests/test_site_design.py`** fails the build on
rules 1 and 2, on a dark token defined in only one place, on a component missing from the style
guide, and on a page without a layout. Run it after any site change.

### Files

| File | Role |
|---|---|
| `assets/css/main.css` | Tokens, then components. The whole design lives here; read its header comment. |
| `style-guide.html` | The living inventory. Every component appears here. |
| `_layouts/default.html` | Shell: header, nav, footer, theming. |
| `_layouts/page.html` | Prose pages (`.prose`, capped measure). |
| `_layouts/post.html` | News posts. |
| `_includes/logo.svg` | Brand mark, themed through tokens. |
| `assets/img/favicon.svg` | Standalone icon — the one file that must hard-code colour, since CSS variables do not reach it. Update it when the palette changes. |
| `assets/js/theme.js` | Light/dark toggle. |
| `assets/js/releases.js` | Reads the GitHub API to fill the download page. |

## Adding a page

Create `your-page.html` (or `.md`) in this folder with front matter:

```yaml
---
layout: page
title: Your page
subtitle: One sentence that sets it up.
permalink: /your-page/
description: One sentence for search engines and link previews.
---
```

Then compose the body from components on the style guide. Add it to the nav in
`_layouts/default.html` only if a visitor needs it; maintainer pages belong in the footer.

## Writing a news post

Add one Markdown file to `_posts/`, named `YYYY-MM-DD-some-slug.md`:

```markdown
---
title: "Calotriton asper module 1.1"
date: 2026-09-12
tag: Species module
---

What changed, in a paragraph or two.
```

Commit and push. It appears on `/news/`, in the RSS feed, and nowhere else needs touching. `tag` is
optional and renders as a small label — "Release", "Species module", "Project".

## Announcing a release

Nothing to edit. The download page reads the GitHub API at page load, so publishing a release on
GitHub — with the packaged `.zip` attached as a release asset — updates the site by itself, including
the version, date, file size and download button.

Do **not** commit the built `.exe` or its zip to this repository: the bundle is hundreds of
megabytes and would live in the git history forever. Attach it to a release instead
(2 GB per file, unmetered downloads on public repos).

## Previewing locally

**With Ruby:**

```powershell
cd site
bundle install
bundle exec jekyll serve
```

Then open <http://127.0.0.1:4000/HerpetoID/>.

**Without Ruby**, `build/site-preview/render.py` (git-ignored, not part of the project) renders a
flat-file approximation good enough to check layout and design, and `shot.py` screenshots it with
the QtWebEngine that PySide6 already ships:

```powershell
.venv\Scripts\python build\site-preview\render.py
.venv\Scripts\python build\site-preview\shot.py index.html dark 1280
```

It implements only the Liquid subset the site uses — GitHub Actions does the real build, so check
the Actions log after pushing.

## One-time setup

In the repository on GitHub: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
After that, every push to `main` that touches `site/` redeploys automatically (about a minute).

## Custom domain

If a domain is ever pointed at the site: add a `CNAME` file here containing the bare domain, set
`url` in `_config.yml` to it and set `baseurl` to `""`.
