"""Tests for the bundled user manual loader."""

from __future__ import annotations

from herpetoid.infrastructure.docs import load_manual


def test_load_manual() -> None:
    chapters = load_manual()
    assert len(chapters) >= 5
    assert chapters[0].title == "Getting Started"
    assert "workflow" in chapters[0].markdown.lower()
    assert all(chapter.markdown.strip() for chapter in chapters)
