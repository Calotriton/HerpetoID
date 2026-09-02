"""What date a photograph should be recorded under.

Two sources, in this order:

1. **The path** — the file's own name, then the folders it was found in
   (:mod:`herpetoid.application.date_inference`). A researcher who names a folder
   ``2023-07-15 Riu Aigües`` is making a deliberate statement about that session.
2. **The camera's EXIF metadata** — ``DateTimeOriginal``, the moment the shutter fired.

The path wins because it is the one a person chose, and because a camera whose clock was never set
after a battery change reports its dates with total confidence and total inaccuracy. EXIF is what
answers for the very common case of an untouched card dump — ``DSC_0031.JPG`` in ``DCIM/100CANON`` —
where the path says nothing at all.

Either way the date is only a starting value: it is written into the observation's Date field, which
the researcher can change on the Observations tab.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from logging import getLogger
from pathlib import Path

from PIL import Image as PilImage

from herpetoid.application.date_inference import infer_date_from_path, plausible_date

_LOGGER = getLogger("herpetoid.capture_date")

#: EXIF tags carrying a capture time, best first. ``DateTimeOriginal`` and ``DateTimeDigitized`` live
#: in the Exif sub-IFD; plain ``DateTime`` sits in IFD0 and is the file's *modification* time, which
#: an editing program will have rewritten -- hence last.
_DATE_TIME_ORIGINAL = 0x9003
_DATE_TIME_DIGITIZED = 0x9004
_DATE_TIME = 0x0132
_EXIF_IFD = 0x8769


@dataclass(frozen=True, slots=True)
class CaptureDate:
    """A date found for a photograph, and where it came from (so the interface can say)."""

    value: date
    source: str


def capture_date_for(path: Path, *, today: date | None = None) -> CaptureDate | None:
    """The date to record for ``path``: what its path states, else what its camera recorded."""
    from_path = infer_date_from_path(path, today=today)
    if from_path is not None:
        return CaptureDate(from_path, "file name/folder")
    from_exif = read_exif_date(path, today=today)
    if from_exif is not None:
        return CaptureDate(from_exif, "camera (EXIF)")
    return None


def read_exif_date(path: Path, *, today: date | None = None) -> date | None:
    """The capture date in ``path``'s EXIF metadata, or ``None``.

    Only the header is read -- the image is never decoded -- so this stays cheap enough to run over
    a whole card dump while staging. Anything unreadable, missing or nonsensical (an unset camera
    clock writes ``0000:00:00``) yields ``None`` rather than an error: a file that fails here can
    still be imported, just without a date.
    """
    try:
        with PilImage.open(path) as image:
            exif = image.getexif()
            sub = exif.get_ifd(_EXIF_IFD)
            raw = (
                sub.get(_DATE_TIME_ORIGINAL)
                or sub.get(_DATE_TIME_DIGITIZED)
                or exif.get(_DATE_TIME)
            )
    except Exception as exc:  # not an image, truncated, no EXIF block, a decompression bomb ...
        _LOGGER.debug("No EXIF date read from %s: %s", path, exc)
        return None
    return _parse_exif_timestamp(raw, today=today)


def _parse_exif_timestamp(raw: object, *, today: date | None = None) -> date | None:
    """The date part of an EXIF ``YYYY:MM:DD HH:MM:SS`` timestamp, validated like any other date."""
    if isinstance(raw, bytes):
        raw = raw.decode("ascii", errors="ignore")
    if not isinstance(raw, str):
        return None
    day_part = raw.strip().split(" ")[0].replace("-", ":").replace("/", ":")
    parts = day_part.split(":")
    if len(parts) != 3:
        return None
    try:
        year, month, day = (int(part) for part in parts)
    except ValueError:
        return None
    return plausible_date(year, month, day, today=today)
