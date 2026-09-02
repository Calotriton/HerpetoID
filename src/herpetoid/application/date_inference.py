"""Read the capture date out of an image's file name or the folders it was found in.

Cameras and field workflows put the date in the path far more often than not
(``IMG_20230715_142530.JPG``, ``2023-07-15 Riu Aigües/CAM1/DSC_0001.JPG``, ``15-07-2023/…``), so the
import can fill in each observation's date instead of leaving the researcher to type it once per
photograph. Nothing here guesses: a candidate must be a *real* calendar date in a plausible year, or
no date is offered and the field simply stays as it was.

Qt-free and pure — the GUI only calls :func:`infer_date_from_path`.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

#: How many folders above the file are searched. Deep enough for ``<date>/<site>/<camera>/photo.jpg``,
#: shallow enough that a far-off ancestor (``D:/Fieldwork 2019-2020/…``) cannot donate its date to
#: everything nested below it.
MAX_PARENTS = 3

#: No camera predates this, and a date before it is far likelier to be a serial number that happens
#: to parse. The upper bound is "next year" (see :func:`_max_year`) to tolerate a clock set ahead.
_MIN_YEAR = 1990

#: Month names by their first three letters, covering English, Spanish and Catalan — enough for
#: ``15-jul-2023``, ``15_julio_2023`` and ``15 juliol 2023`` alike.
_MONTH_BY_PREFIX: dict[str, int] = {
    "jan": 1, "ene": 1, "gen": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4, "abr": 4,
    "may": 5, "mai": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8, "ago": 8,
    "sep": 9, "set": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12, "dic": 12, "des": 12,
}

# Every pattern is anchored with (?<!\d)/(?!\d) so it can only match a *whole* run of digits: that is
# what stops "IMG_123456789" or a resolution like "19201080" from being read as a date.
_YEAR_FIRST = re.compile(r"(?<!\d)(\d{4})[-_.](\d{1,2})[-_.](\d{1,2})(?!\d)")
_DAY_FIRST = re.compile(r"(?<!\d)(\d{1,2})[-_.](\d{1,2})[-_.](\d{4})(?!\d)")
_YEAR_FIRST_NAMED = re.compile(r"(?<!\d)(\d{4})[-_. ]*([A-Za-z\u00c0-\u024f]{3,12})[-_. ]*(\d{1,2})(?!\d)")
_DAY_FIRST_NAMED = re.compile(r"(?<!\d)(\d{1,2})[-_. ]*([A-Za-z\u00c0-\u024f]{3,12})[-_. ]*(\d{4})(?!\d)")
_COMPACT = re.compile(r"(?<!\d)(\d{8})(?!\d)")


def plausible_date(year: int, month: int, day: int, *, today: date | None = None) -> date | None:
    """``date(year, month, day)`` when that is a real date a camera could plausibly have recorded.

    Shared with the EXIF reader (:mod:`herpetoid.infrastructure.capture_date`) so a date claimed by a
    camera and a date written in a folder name are held to exactly the same standard.
    """
    return _make_date(year, month, day, _max_year(today))


def parse_date(text: str, *, today: date | None = None) -> date | None:
    """The first real calendar date written in ``text``, or ``None``.

    Understood: ``2023-07-15`` / ``2023_07_15`` / ``2023.07.15``, ``15-07-2023``, ``20230715``,
    ``15072023``, and the same shapes with a month *name* (``15-jul-2023``, ``2023 juliol 15``).

    A purely numeric ``05-07-2023`` is ambiguous; it is read **day-first** (5 July), the convention
    of the DD/MM/YYYY format this application displays. The one exception is a first number that
    cannot be a day paired with a second that can only be a month position — ``07-15-2023`` is read
    as 15 July rather than discarded.
    """
    max_year = _max_year(today)
    for match in _YEAR_FIRST.finditer(text):
        year, month, day = (int(part) for part in match.groups())
        if (found := _make_date(year, month, day, max_year)) is not None:
            return found
    for match in _DAY_FIRST.finditer(text):
        first, second, year = (int(part) for part in match.groups())
        found = _make_date(year, second, first, max_year)  # day-first by default
        if found is None:  # ...unless only the month-day reading is a real date (US-style names)
            found = _make_date(year, first, second, max_year)
        if found is not None:
            return found
    for match in _YEAR_FIRST_NAMED.finditer(text):
        named = _month_number(match.group(2))
        if named is not None:
            found = _make_date(int(match.group(1)), named, int(match.group(3)), max_year)
            if found is not None:
                return found
    for match in _DAY_FIRST_NAMED.finditer(text):
        named = _month_number(match.group(2))
        if named is not None:
            found = _make_date(int(match.group(3)), named, int(match.group(1)), max_year)
            if found is not None:
                return found
    for match in _COMPACT.finditer(text):
        digits = match.group(1)
        found = _make_date(int(digits[:4]), int(digits[4:6]), int(digits[6:]), max_year)
        if found is None:  # not YYYYMMDD -- try DDMMYYYY
            found = _make_date(int(digits[4:]), int(digits[2:4]), int(digits[:2]), max_year)
        if found is not None:
            return found
    return None


def infer_date_from_path(
    path: Path, *, today: date | None = None, max_parents: int = MAX_PARENTS
) -> date | None:
    """The capture date implied by ``path``: its file name first, then its folders, nearest first.

    The file name wins because it is the more specific statement about *this* photograph: a
    ``2023-07-15 Riu Aigües`` folder holding an ``IMG_20230716_0031.JPG`` shot after midnight is
    describing the session, not the frame.
    """
    path = Path(path)
    candidates = [path.stem, *(parent.name for parent in path.parents[:max_parents])]
    for text in candidates:
        if not text:
            continue
        if (found := parse_date(text, today=today)) is not None:
            return found
    return None


def _month_number(name: str) -> int | None:
    return _MONTH_BY_PREFIX.get(name[:3].lower())


def _max_year(today: date | None) -> int:
    return (today or date.today()).year + 1


def _make_date(year: int, month: int, day: int, max_year: int) -> date | None:
    """``date(year, month, day)`` when that is a real date in a plausible year, else ``None``."""
    if not _MIN_YEAR <= year <= max_year:
        return None
    try:
        return date(year, month, day)
    except ValueError:  # 31 February, month 13, day 0 ...
        return None
