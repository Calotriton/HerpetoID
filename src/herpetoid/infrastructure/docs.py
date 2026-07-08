"""Access to the bundled Markdown user manual (packaged under herpetoid/resources/docs)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.resources import files


@dataclass(frozen=True, slots=True)
class ManualChapter:
    title: str
    markdown: str


def load_manual() -> list[ManualChapter]:
    """Load the ordered manual chapters from the packaged resources."""
    root = files("herpetoid").joinpath("resources", "docs")
    manifest = json.loads(root.joinpath("manifest.json").read_text(encoding="utf-8"))
    chapters: list[ManualChapter] = []
    for entry in manifest:
        markdown = root.joinpath(entry["file"]).read_text(encoding="utf-8")
        chapters.append(ManualChapter(title=str(entry["title"]), markdown=markdown))
    return chapters
