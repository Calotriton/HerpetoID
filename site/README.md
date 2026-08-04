# HerpetoID website

The public site at <https://calotriton.github.io/HerpetoID/>. Jekyll, published by GitHub Pages via
[`.github/workflows/pages.yml`](../.github/workflows/pages.yml). Only this folder is published — the
Python package, the tests and the internal notes in `docs/` are never part of the site.

## One-time setup

In the repository on GitHub: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
After that, every push to `main` that touches `site/` redeploys automatically (about a minute).

## Announcing a release

Nothing to edit. The download page reads the GitHub API at page load, so publishing a release on
GitHub — with the packaged `.zip` attached as a release asset — updates the site by itself, including
the version, date, file size and download button.

Do **not** commit the built `.exe` or its zip to this repository: the bundle is hundreds of
megabytes and would live in the git history forever. Attach it to a release instead
(2 GB per file, unmetered downloads on public repos).

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
optional and just renders a small label — "Release", "Species module", "Project".

## Editing the pages

| File | Page |
|---|---|
| `index.html` | Landing page |
| `how-it-works.md` | `/how-it-works/` |
| `download.html` | `/download/` |
| `news.md` | `/news/` (lists `_posts/`) |
| `assets/css/main.css` | Styling — the palette mirrors the app's "Brook Teal" theme |
| `assets/js/releases.js` | Fetches releases from the GitHub API |

Screenshots go in `assets/img/` and are referenced as
`{% raw %}{{ '/assets/img/name.png' | relative_url }}{% endraw %}`. The hero illustration in
`index.html` is a placeholder to swap out once there are real screenshots.

## Previewing locally (optional)

Needs Ruby. Without it, push to a branch and check the Actions log for build errors.

```powershell
cd site
bundle install
bundle exec jekyll serve
```

Then open <http://127.0.0.1:4000/HerpetoID/>.

## Custom domain

If a domain is ever pointed at the site: add a `CNAME` file here containing the bare domain, set
`url` in `_config.yml` to it and set `baseurl` to `""`.
