"""Guard tests for the website's design system.

The site is a design system, not a pile of pages: tokens own every colour, components own their
styling, and pages only compose components. That is easy to say and easy to erode — one hurried
`style="margin-top:2rem"`, one hard-coded `#2f9e8f`, and the next change has to work around it.

These tests fail the moment that starts. They are deliberately cheap and structural: they check
where values live, never what the design looks like. See `site/style-guide.html` for the system
itself and `site/README.md` for the working rules.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SITE = Path(__file__).resolve().parents[1] / "site"
CSS = SITE / "assets" / "css" / "main.css"

#: Everything above this marker in main.css is the token block, the one place colours are written.
TOKENS_END = "=== END OF TOKENS ==="

#: Colours are allowed inside SVG markup only through `var(--token)`. The lookbehind keeps HTML
#: numeric entities (`&#9678;`) from reading as hex colours.
HEX = re.compile(r"(?<!&)#[0-9a-fA-F]{3,8}\b")
RGB_FUNC = re.compile(r"\brgba?\(")


def _site_files(*patterns: str) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        files.extend(sorted(SITE.glob(pattern)))
    assert files, f"no site files matched {patterns!r} — did the site move?"
    return files


def _pages() -> list[Path]:
    """The published pages. site/README.md is maintainer documentation, not a page, and it quotes
    token values on purpose; assets/img/favicon.svg is a standalone icon where CSS variables do not
    apply, so both stay out of these checks."""
    files = _site_files("*.html", "*.md", "_layouts/*.html", "_includes/*.svg", "_posts/*.md")
    return [path for path in files if path.name != "README.md"]


def test_pages_never_use_inline_styles() -> None:
    """An inline style is a component that was never written down."""
    offenders = [
        f"{path.relative_to(SITE)}: {match.group(0)}"
        for path in _pages()
        for match in re.finditer(r'style\s*=\s*"[^"]*"', path.read_text(encoding="utf-8"))
    ]
    assert not offenders, "use a component or a utility class instead of inline styles:\n" + "\n".join(
        offenders
    )


def test_pages_never_hard_code_colours() -> None:
    """Colour belongs to the token block; markup asks for it by name.

    Inline SVG is the one place a page may name a colour — and it must still do so as
    ``var(--token)``, so a theme change reaches the diagrams too.
    """
    offenders = []
    for path in _pages():
        for line in path.read_text(encoding="utf-8").splitlines():
            # <meta name="theme-color"> cannot reference a CSS variable; it is checked against the
            # tokens by test_theme_color_meta_matches_the_tokens instead.
            if "theme-color" in line:
                continue
            for match in HEX.finditer(line):
                offenders.append(f"{path.relative_to(SITE)}: {match.group(0)}")
            for match in RGB_FUNC.finditer(line):
                offenders.append(f"{path.relative_to(SITE)}: {match.group(0)}…")
    assert not offenders, (
        "hard-coded colours in markup — add a token in main.css and use var(--token):\n"
        + "\n".join(offenders)
    )


def _token(block_start: str, name: str) -> str:
    """The value of one custom property inside the CSS block that starts with ``block_start``."""
    css = CSS.read_text(encoding="utf-8")
    start = css.index(block_start)
    match = re.search(rf"{name}\s*:\s*([^;]+);", css[start:])
    assert match, f"token {name} not found after {block_start!r}"
    return match.group(1).strip()


def test_theme_color_meta_matches_the_tokens() -> None:
    """The browser-chrome colour is the one value markup must repeat — so it must not drift.

    ``<meta name="theme-color">`` tints the mobile browser's own UI and cannot read a CSS variable.
    If the page background changes and this does not, the phone's chrome shows the old palette
    around the new page.
    """
    layout = (SITE / "_layouts" / "default.html").read_text(encoding="utf-8")
    declared = dict(
        re.findall(
            r'<meta name="theme-color" content="(#[0-9a-fA-F]{3,8})" media="\(prefers-color-scheme: (\w+)\)">',
            layout,
        )
    )
    assert set(declared.values()) == {"light", "dark"}, "expected a light and a dark theme-color"
    values = {scheme: colour for colour, scheme in declared.items()}
    assert values["light"] == _token(":root {", "--bg")
    assert values["dark"] == _token(':root[data-theme="dark"] {', "--bg")


def test_stylesheet_keeps_colour_in_the_token_block() -> None:
    """Components must not invent colours: below the token block, colour comes from var()."""
    css = CSS.read_text(encoding="utf-8")
    assert TOKENS_END in css, "the token block marker moved — update this test with it"
    components = css.split(TOKENS_END, 1)[1]
    # Data-URI icons are themed by swapping the whole token, so they legitimately carry a colour.
    components = re.sub(r"url\(\"data:image/svg\+xml.*?\"\)", "", components, flags=re.S)
    # Print has no theme — paper is white and ink is black whatever the reader chose.
    components = components.split("@media print")[0]
    offenders = [m.group(0) for m in HEX.finditer(components)]
    offenders += [m.group(0) + "…" for m in RGB_FUNC.finditer(components)]
    assert not offenders, (
        "colour literals outside the token block in main.css — define a token instead:\n"
        + "\n".join(offenders)
    )


def test_every_theme_override_exists_in_both_places() -> None:
    """A token overridden for dark mode must be overridden in both dark selectors.

    The site supports "follow the system" *and* an explicit toggle, so dark values live twice: under
    ``prefers-color-scheme`` and under ``[data-theme="dark"]``. Updating only one is invisible until
    a user with the opposite setting looks at it.
    """
    css = CSS.read_text(encoding="utf-8")

    def tokens_in(block_start: str) -> set[str]:
        start = css.index(block_start) + len(block_start)
        depth, index = 0, start
        while index < len(css):
            if css[index] == "{":
                depth += 1
            elif css[index] == "}":
                if depth == 0:
                    break
                depth -= 1
            index += 1
        return set(re.findall(r"(--[a-z0-9-]+)\s*:", css[start:index]))

    media = tokens_in('@media (prefers-color-scheme: dark) {\n  :root:not([data-theme="light"]) {')
    explicit = tokens_in(':root[data-theme="dark"] {')
    assert media, "the prefers-color-scheme dark block was not found"
    assert media == explicit, (
        "dark-mode tokens differ between the media query and the [data-theme] block: "
        f"{sorted(media ^ explicit)}"
    )


def test_style_guide_shows_every_component() -> None:
    """The style guide is the inventory future pages compose from — it has to stay complete."""
    guide = (SITE / "style-guide.html").read_text(encoding="utf-8")
    for component in (
        "btn",
        "btn-secondary",
        "pill",
        "tag",
        "status",
        "card",
        "card-icon",
        "panel",
        "steps",
        "spec-list",
        "callout",
        "table-scroll",
        "label",
        "lede",
    ):
        assert f'"{component}' in guide or f' {component}"' in guide, (
            f"component .{component} is not demonstrated on /style-guide/"
        )


@pytest.mark.parametrize("page", [p for p in _pages() if p.suffix == ".html"])
def test_pages_declare_a_layout(page: Path) -> None:
    """Every page runs through a layout, so the header, footer and theming are never bypassed."""
    text = page.read_text(encoding="utf-8")
    if text.lstrip().startswith("<!doctype"):  # the layout itself
        return
    assert text.startswith("---"), f"{page.name} has no front matter"
    front_matter = text.split("---", 2)[1]
    assert "layout:" in front_matter, f"{page.name} declares no layout"
