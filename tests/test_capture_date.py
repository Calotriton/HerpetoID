"""The date a photograph is recorded under: its path first, its camera's EXIF second."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PilImage

from herpetoid.infrastructure.capture_date import capture_date_for, read_exif_date

TODAY = date(2026, 9, 2)


def _photo(path: Path, *, original: str | None = None, digitized: str | None = None,
           modified: str | None = None) -> Path:
    """A real JPEG, optionally carrying the three EXIF timestamps a camera can write."""
    path.parent.mkdir(parents=True, exist_ok=True)
    exif = PilImage.Exif()
    if modified is not None:
        exif[0x0132] = modified  # DateTime, in IFD0
    sub = exif.get_ifd(0x8769)
    if original is not None:
        sub[0x9003] = original  # DateTimeOriginal
    if digitized is not None:
        sub[0x9004] = digitized  # DateTimeDigitized
    PilImage.fromarray(np.zeros((16, 16, 3), np.uint8)).save(path, "JPEG", exif=exif)
    return path


def test_reads_the_moment_the_shutter_fired(tmp_path: Path) -> None:
    photo = _photo(tmp_path / "DSC_0001.jpg", original="2023:07:15 14:25:30")
    assert read_exif_date(photo, today=TODAY) == date(2023, 7, 15)


def test_prefers_original_then_digitized_then_the_file_timestamp(tmp_path: Path) -> None:
    """DateTime is the *modification* time — an editor rewrites it, so it is the last resort."""
    everything = _photo(
        tmp_path / "all.jpg",
        original="2023:07:15 14:25:30",
        digitized="2023:07:18 08:00:00",
        modified="2024:01:20 09:00:00",
    )
    assert read_exif_date(everything, today=TODAY) == date(2023, 7, 15)

    no_original = _photo(
        tmp_path / "scanned.jpg", digitized="2023:07:18 08:00:00", modified="2024:01:20 09:00:00"
    )
    assert read_exif_date(no_original, today=TODAY) == date(2023, 7, 18)

    edited = _photo(tmp_path / "edited.jpg", modified="2024:01:20 09:00:00")
    assert read_exif_date(edited, today=TODAY) == date(2024, 1, 20)


@pytest.mark.parametrize(
    "stamp",
    [
        "0000:00:00 00:00:00",  # a camera whose clock was never set
        "2023:13:45 10:00:00",  # not a real date
        "2030:07:15 10:00:00",  # a clock set years ahead
        "1975:07:15 10:00:00",  # before any digital capture this application would see
        "not a timestamp",
        "",
    ],
)
def test_a_nonsensical_stamp_yields_no_date(tmp_path: Path, stamp: str) -> None:
    photo = _photo(tmp_path / "odd.jpg", original=stamp)
    assert read_exif_date(photo, today=TODAY) is None


def test_a_photograph_without_exif_or_an_unreadable_file_is_not_an_error(tmp_path: Path) -> None:
    plain = tmp_path / "plain.png"
    PilImage.fromarray(np.zeros((16, 16, 3), np.uint8)).save(plain)
    assert read_exif_date(plain, today=TODAY) is None

    truncated = tmp_path / "truncated.jpg"
    truncated.write_bytes(b"\xff\xd8\xff garbage")
    assert read_exif_date(truncated, today=TODAY) is None  # staging must never break on a bad file
    assert read_exif_date(tmp_path / "missing.jpg", today=TODAY) is None


# --- the two sources together ----------------------------------------------------------------------


def test_the_path_wins_over_the_camera_clock(tmp_path: Path) -> None:
    """A folder a person named beats a camera clock that may never have been set."""
    photo = _photo(
        tmp_path / "2023-07-15 Riu Aigues" / "DSC_0001.jpg", original="2000:01:01 00:00:00"
    )
    found = capture_date_for(photo, today=TODAY)
    assert found is not None
    assert (found.value, found.source) == (date(2023, 7, 15), "file name/folder")


def test_exif_answers_for_an_untouched_card_dump(tmp_path: Path) -> None:
    """The case the path cannot help with: DCIM/100CANON/DSC_0031.JPG."""
    photo = _photo(tmp_path / "DCIM" / "100CANON" / "DSC_0031.jpg", original="2023:07:15 14:25:30")
    found = capture_date_for(photo, today=TODAY)
    assert found is not None
    assert (found.value, found.source) == (date(2023, 7, 15), "camera (EXIF)")


def test_no_date_anywhere_stays_empty(tmp_path: Path) -> None:
    plain = tmp_path / "DCIM" / "DSC_0031.png"
    plain.parent.mkdir(parents=True)
    PilImage.fromarray(np.zeros((16, 16, 3), np.uint8)).save(plain)
    assert capture_date_for(plain, today=TODAY) is None
