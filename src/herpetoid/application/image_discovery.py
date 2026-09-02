"""Find the image files a researcher wants to import from a chosen folder.

A field session almost never leaves its photographs in one flat folder: a card dump ends up as
``2023-07-15 Riu Aigües/CAM1/…``, one folder per site, per camera or per day. This module answers the
one question the import screen needs — *which image files are in this folder, including everything
below it* — so picking the session folder is enough to stage the whole session.

Qt-free and side-effect free: it only reads the directory tree.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path

#: Extensions the import pipeline can decode. Kept in step with the import screen's dialog filter.
IMAGE_EXTENSIONS: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"})


def is_image(path: Path) -> bool:
    """Whether ``path`` looks like an image this application can import, by extension."""
    return path.suffix.lower() in IMAGE_EXTENSIONS


def collect_images(
    root: Path,
    *,
    recursive: bool = True,
    extensions: Iterable[str] = IMAGE_EXTENSIONS,
) -> list[Path]:
    """Every image file inside ``root``, sorted, deepest structure included.

    ``root`` may also be a single image file, in which case it is returned on its own — that keeps
    callers from having to special-case a one-file "folder".

    Hidden folders (``.git``, ``.thumbnails``, macOS ``.Spool`` leftovers) are skipped, symlinked
    directories are not followed, and a directory already visited is never descended into twice, so
    a linked folder can neither send the walk into a loop nor drag in a tree outside the selection.
    """
    root = Path(root)
    suffixes = frozenset(suffix.lower() for suffix in extensions)
    if not root.is_dir():
        return [root] if root.is_file() and root.suffix.lower() in suffixes else []

    found: list[Path] = []
    visited: set[Path] = set()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        here = Path(dirpath)
        real = _real_path(here)
        if real in visited:  # a junction/symlink pointing back up the tree
            dirnames[:] = []
            continue
        visited.add(real)
        dirnames[:] = [] if not recursive else sorted(d for d in dirnames if not d.startswith("."))
        found.extend(
            here / name for name in filenames if Path(name).suffix.lower() in suffixes
        )
    return sorted(found)


def _real_path(path: Path) -> Path:
    """``path`` with links resolved, falling back to the path itself when the OS refuses."""
    try:
        return path.resolve()
    except OSError:  # a broken link or a path the filesystem won't stat
        return path
