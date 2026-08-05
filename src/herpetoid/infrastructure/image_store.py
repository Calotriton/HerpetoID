"""File-based image store for a project bundle.

Implements the :class:`~herpetoid.application.ports.ImageStore` port. Images are copied into the
bundle's ``images/`` directory (named by content hash for de-duplication); thumbnails go to
``thumbnails/``. All paths returned are bundle-relative so the bundle stays portable.
"""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image as PilImage
from PIL import ImageOps

from herpetoid.infrastructure.paths import resolve_in_bundle

_THUMBNAIL_SIZE = (256, 256)
_HASH_CHUNK = 1024 * 1024

#: Refuse to decode images beyond this pixel count. Well above any real camera (the largest medium
#: format sensors are ~100 MP) and below Pillow's own hard bomb limit, so an image whose header
#: declares an absurd size is rejected with a clear message *before* anything is decompressed.
_MAX_PIXELS = 150_000_000


class ImageTooLargeError(OSError):
    """Raised when an image's declared dimensions exceed the decode budget (decompression bomb)."""


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

    def resolve(self, rel_path: str) -> Path:
        """The absolute path of a bundle-relative path, guaranteed to stay inside the bundle."""
        return resolve_in_bundle(self._root, rel_path)

    def load(self, rel_path: str) -> np.ndarray:
        """Load a bundle-relative image as an RGB ``uint8`` array."""
        with PilImage.open(self.resolve(rel_path)) as image:
            _check_pixel_budget(image.size, rel_path)
            return np.asarray(image.convert("RGB"))

    def save(self, source: Path, rel_path: str) -> None:
        """Copy an external file to a bundle-relative path."""
        dest = self.resolve(rel_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)

    def import_image(self, source: Path) -> ImportedImage:
        """Copy ``source`` into the bundle, honoring EXIF orientation, and build a thumbnail."""
        # Hash and copy by streaming rather than holding the file in memory: raw scientific captures
        # run to hundreds of megabytes and a batch import would otherwise buffer every one of them.
        file_hash = _hash_file(source)
        with PilImage.open(source) as opened:
            _check_pixel_budget(opened.size, str(source))  # before any decompression happens
            oriented = ImageOps.exif_transpose(opened)
            image = oriented if oriented is not None else opened
            width, height = image.size
            image_format = (image.format or source.suffix.lstrip(".")).lower()
            rgb = image.convert("RGB")

            extension = source.suffix.lower() or ".png"
            rel_path = f"images/{file_hash}{extension}"
            destination = self.resolve(rel_path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.copyfile(source, destination)

            thumbnail = rgb.copy()
            thumbnail.thumbnail(_THUMBNAIL_SIZE)
            thumbnail_rel = f"thumbnails/{file_hash}.jpg"
            thumbnail_path = self.resolve(thumbnail_rel)
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


def _hash_file(path: Path) -> str:
    """SHA-256 of a file's contents, read in chunks."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_HASH_CHUNK), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_pixel_budget(size: tuple[int, int], label: str) -> None:
    """Reject an image whose declared dimensions exceed :data:`_MAX_PIXELS`."""
    width, height = size
    if width * height > _MAX_PIXELS:
        raise ImageTooLargeError(
            f"{label}: image is {width}x{height} ({width * height:,} pixels), which exceeds the "
            f"{_MAX_PIXELS:,}-pixel limit"
        )
