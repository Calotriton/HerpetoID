"""Picking a folder of photographs and reading the date out of the paths inside it.

Both behaviours are Qt-free, so they are tested here as pure functions; the screen wiring that uses
them is covered in ``test_gui.py`` and ``test_end_to_end.py``.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from herpetoid.application.date_inference import infer_date_from_path, parse_date
from herpetoid.application.image_discovery import IMAGE_EXTENSIONS, collect_images, is_image


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not really an image, but collect_images only reads the tree")
    return path


# --- collecting a folder tree ---------------------------------------------------------------------


def test_collect_images_walks_subfolders(tmp_path: Path) -> None:
    """The point of the feature: one folder, every image under it, however deep."""
    expected = {
        _touch(tmp_path / "top.jpg"),
        _touch(tmp_path / "2023-07-15" / "CAM1" / "a.JPG"),
        _touch(tmp_path / "2023-07-15" / "CAM1" / "b.jpeg"),
        _touch(tmp_path / "2023-07-15" / "CAM2" / "deep" / "deeper" / "c.png"),
        _touch(tmp_path / "other site" / "d.TIF"),
    }
    _touch(tmp_path / "2023-07-15" / "notes.txt")  # not an image
    _touch(tmp_path / "2023-07-15" / "CAM1" / "raw.cr2")  # not a format we can decode
    _touch(tmp_path / ".thumbnails" / "hidden.jpg")  # a hidden helper folder

    found = collect_images(tmp_path)
    assert set(found) == expected
    assert found == sorted(found)  # deterministic order, so the staged strip is predictable


def test_collect_images_can_stay_shallow_and_handles_odd_roots(tmp_path: Path) -> None:
    _touch(tmp_path / "top.jpg")
    _touch(tmp_path / "sub" / "nested.jpg")

    assert [p.name for p in collect_images(tmp_path, recursive=False)] == ["top.jpg"]
    # A single file is returned on its own, and a missing path is simply empty -- callers never
    # have to special-case either.
    assert collect_images(tmp_path / "top.jpg") == [tmp_path / "top.jpg"]
    assert collect_images(tmp_path / "top.jpg" / "nope") == []
    assert collect_images(tmp_path / "does-not-exist") == []


def test_collect_images_ignores_an_empty_tree(tmp_path: Path) -> None:
    (tmp_path / "empty" / "also empty").mkdir(parents=True)
    _touch(tmp_path / "empty" / "readme.md")
    assert collect_images(tmp_path) == []


def test_is_image_matches_the_declared_extensions() -> None:
    assert is_image(Path("a.JPG")) and is_image(Path("a.tiff"))
    assert not is_image(Path("a.cr2")) and not is_image(Path("a"))
    assert ".jpg" in IMAGE_EXTENSIONS and ".cr2" not in IMAGE_EXTENSIONS


# --- reading a date out of a name ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # ISO-ish, the most common camera/field convention
        ("2023-07-15", date(2023, 7, 15)),
        ("2023_07_15 Riu Aigues", date(2023, 7, 15)),
        ("2023.07.15", date(2023, 7, 15)),
        ("IMG_2023-7-5_0001", date(2023, 7, 5)),
        # day-first, written out
        ("15-07-2023", date(2023, 7, 15)),
        ("15_07_2023 CAM1", date(2023, 7, 15)),
        # compact, as phones and cameras name their files
        ("IMG_20230715_142530", date(2023, 7, 15)),
        ("20230715", date(2023, 7, 15)),
        ("DSC_15072023", date(2023, 7, 15)),
        # month names: English, Spanish, Catalan
        ("15-jul-2023", date(2023, 7, 15)),
        ("15 julio 2023", date(2023, 7, 15)),
        ("15 juliol 2023", date(2023, 7, 15)),
        ("2023-Jul-15", date(2023, 7, 15)),
        ("1-ene-2024", date(2024, 1, 1)),
        # ambiguous DD/MM vs MM/DD is read day-first...
        ("05-07-2023", date(2023, 7, 5)),
        # ...unless only the other reading is a real date
        ("07-15-2023", date(2023, 7, 15)),
    ],
)
def test_parse_date_reads_the_usual_spellings(text: str, expected: date) -> None:
    assert parse_date(text, today=date(2026, 9, 2)) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "IMG_0001",
        "DSC01234567",  # a 7-digit sequence number
        "P1010101",
        "IMG_123456789",  # too long to be a date, and must not be truncated into one
        "19201080",  # a resolution, not 1920-10-80
        "2023-13-45",  # not a real date
        "20231315",
        "Riu Aigues CAM1",
        "IMG_1234",
        "2023",  # a year alone says nothing about the day
        "salamandra-15-07",  # no year
        "1975-07-15",  # before the plausible range for a digital capture
    ],
)
def test_parse_date_refuses_to_guess(text: str) -> None:
    assert parse_date(text, today=date(2026, 9, 2)) is None


def test_parse_date_rejects_a_date_in_the_future() -> None:
    assert parse_date("2030-07-15", today=date(2026, 9, 2)) is None
    assert parse_date("2027-07-15", today=date(2026, 9, 2)) == date(2027, 7, 15)  # clock skew is ok


def test_infer_date_prefers_the_file_name_then_walks_up_the_folders() -> None:
    root = Path("D:/field/2023-07-15 Riu Aigues")
    # The file name is the more specific statement about this frame.
    assert infer_date_from_path(root / "CAM1" / "IMG_20230716_0031.jpg") == date(2023, 7, 16)
    # ...and when it says nothing, the folders do -- nearest first.
    assert infer_date_from_path(root / "CAM1" / "IMG_0031.jpg") == date(2023, 7, 15)
    assert infer_date_from_path(root / "CAM1" / "deep" / "IMG_0031.jpg") == date(2023, 7, 15)
    assert infer_date_from_path(Path("D:/field/no dates here/IMG_0031.jpg")) is None


def test_infer_date_does_not_reach_past_distant_ancestors() -> None:
    """A far-off ancestor must not donate its date to everything buried below it."""
    path = Path("D:/2023-07-15/site/camera/burst/IMG_0031.jpg")
    assert infer_date_from_path(path) is None
    assert infer_date_from_path(path, max_parents=4) == date(2023, 7, 15)
