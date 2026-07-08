"""File-based image store for a project bundle.

Implements the :class:`~herpetoid.application.ports.ImageStore` port. Images are copied into the
bundle's ``images/`` directory (named by content hash for de-duplication); thumbnails go to
``thumbnails/``. All paths returned are bundle-relative so the bundle stays portable.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image as PilImage
from PIL import ImageOps

_THUMBNAIL_SIZE = (256, 256)


@dataclass(frozen=True, slots=True)
class ImportedImage:
    """Metadata produced when an image is imported into a bundle."""

    rel_path: str
    original_filename: str
    file_hash: str
    width: int
    height: int
    image_format: str
    thumbnail_path: str


class FileImageStore:
    """Loads, saves and imports images within a single project bundle."""

    def __init__(self, bundle_root: Path) -> None:
        self._root = bundle_root

    def load(self, rel_path: str) -> np.ndarray:
        """Load a bundle-relative image as an RGB ``uint8`` array."""
        with PilImage.open(self._root / rel_path) as image:
            return np.asarray(image.convert("RGB"))

    def save(self, source: Path, rel_path: str) -> None:
        """Copy an external file to a bundle-relative path."""
        dest = self._root / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(source.read_bytes())

    def import_image(self, source: Path) -> ImportedImage:
        """Copy ``source`` into the bundle, honoring EXIF orientation, and build a thumbnail."""
        data = source.read_bytes()
        file_hash = hashlib.sha256(data).hexdigest()
        with PilImage.open(io.BytesIO(data)) as opened:
            oriented = ImageOps.exif_transpose(opened)
            image = oriented if oriented is not None else opened
            width, height = image.size
            image_format = (image.format or source.suffix.lstrip(".")).lower()
            rgb = image.convert("RGB")

            extension = source.suffix.lower() or ".png"
            rel_path = f"images/{file_hash}{extension}"
            destination = self._root / rel_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                destination.write_bytes(data)

            thumbnail = rgb.copy()
            thumbnail.thumbnail(_THUMBNAIL_SIZE)
            thumbnail_rel = f"thumbnails/{file_hash}.jpg"
            thumbnail_path = self._root / thumbnail_rel
            thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
            thumbnail.save(thumbnail_path, "JPEG", quality=85)

        return ImportedImage(
            rel_path=rel_path,
            original_filename=source.name,
            file_hash=file_hash,
            width=int(width),
            height=int(height),
            image_format=image_format,
            thumbnail_path=thumbnail_rel,
        )
