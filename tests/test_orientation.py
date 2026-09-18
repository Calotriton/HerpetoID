"""Quarter turns applied to a photograph, and the same turn applied to its marked region."""

from __future__ import annotations

import numpy as np
import pytest

from herpetoid.api import ROI, ROIKind
from herpetoid.api.preprocessing import crop_to_roi
from herpetoid.application.orientation import (
    normalize_rotation,
    oriented,
    rotate_image,
    rotate_point,
    rotate_roi,
    unrotate_roi,
)


@pytest.mark.parametrize(
    ("given", "expected"),
    [(0, 0), (90, 90), (180, 180), (270, 270), (360, 0), (-90, 270), (-180, 180), (450, 90)],
)
def test_any_angle_snaps_to_a_quarter_turn(given: int, expected: int) -> None:
    assert normalize_rotation(given) == expected


def test_turning_an_image_swaps_its_sides_for_the_odd_turns() -> None:
    image = np.zeros((80, 100, 3), np.uint8)  # 100 wide, 80 tall
    assert rotate_image(image, 0).shape == (80, 100, 3)
    assert rotate_image(image, 90).shape == (100, 80, 3)
    assert rotate_image(image, 180).shape == (80, 100, 3)
    assert rotate_image(image, 270).shape == (100, 80, 3)


def test_a_turn_moves_the_pixels_the_way_the_button_says() -> None:
    """Clockwise: the top-left corner ends up top-right."""
    image = np.zeros((4, 3), np.uint8)
    image[0, 0] = 255  # top-left
    turned = rotate_image(image, 90)
    assert turned.shape == (3, 4)
    assert turned[0, 3] == 255  # ...now top-right
    assert (rotate_image(image, 360) == image).all()


def test_a_point_follows_the_picture_and_four_turns_come_home() -> None:
    """A drawn vertex is a place on the image plane, not a pixel index.

    So the frame ends at ``height``, not ``height - 1``. Mapping a vertex with ``height - 1 - y``
    slid every region one pixel per quarter turn, moving the crop a matcher reads.
    """
    width, height = 100, 80
    assert rotate_point(0, 0, width, height, 90) == (80, 0)  # top-left corner -> top-right corner
    # Turning by d and then by -d is exact, not approximate: the quarter turns are a group.
    for degrees in (90, 180, 270):
        x, y = rotate_point(37, 11, width, height, degrees)
        w, h = (height, width) if degrees % 180 else (width, height)
        assert rotate_point(x, y, w, h, -degrees) == (37, 11)


def test_a_marked_region_turns_with_its_image() -> None:
    roi = ROI.rectangle(10, 20, 30, 40)
    turned = rotate_roi(roi, 90, 100, 80)
    assert turned is not None
    # The same patch of animal, in the turned frame: the box's sides swap over.
    assert turned.bounding_box() == (20, 10, 40, 30)
    assert roi.bounding_box() == (10, 20, 30, 40)  # the original is untouched


def test_a_polygon_keeps_its_shape_and_a_mask_is_turned_too() -> None:
    polygon = ROI(kind=ROIKind.POLYGON, points=((0, 0), (30, 0), (30, 20), (0, 20)))
    turned = rotate_roi(polygon, 90, 100, 80)
    assert turned is not None
    assert turned.kind is ROIKind.POLYGON
    assert len(turned.points) == 4
    assert turned.bounding_box() == (60, 0, 20, 30)  # a 30x20 box becomes 20x30

    mask = np.zeros((80, 100), np.uint8)
    mask[0:10, 0:20] = 1
    masked = rotate_roi(ROI(kind=ROIKind.MASK, mask=mask), 90, 100, 80)
    assert masked is not None and masked.mask is not None
    assert masked.mask.shape == (100, 80)
    assert masked.mask.sum() == mask.sum()  # nothing gained or lost, only moved


def test_a_full_image_region_and_no_turn_are_left_alone() -> None:
    full = ROI.full_image()
    assert rotate_roi(full, 90, 10, 10) is full
    roi = ROI.rectangle(1, 2, 3, 4)
    assert rotate_roi(roi, 0, 10, 10) is roi
    assert rotate_roi(None, 90, 10, 10) is None


def test_oriented_turns_the_pair_together() -> None:
    image = np.zeros((80, 100, 3), np.uint8)
    array, roi = oriented(image, ROI.rectangle(10, 20, 30, 40), 90)
    assert array.shape == (100, 80, 3)
    assert roi is not None and roi.bounding_box() == (20, 10, 40, 30)

    same_array, same_roi = oriented(image, ROI.rectangle(10, 20, 30, 40), 0)
    assert same_array.shape == image.shape
    assert same_roi is not None and same_roi.bounding_box() == (10, 20, 30, 40)


@pytest.mark.parametrize("degrees", [90, 180, 270])
def test_a_region_drawn_on_screen_maps_back_to_the_file_exactly(degrees: int) -> None:
    """The bundle stores file coordinates; a turn on screen must not drift them.

    This is what stops a region creeping across the animal each time a capture is turned and saved.
    """
    width, height = 100, 80
    stored = ROI.rectangle(10, 20, 30, 40)
    on_screen = rotate_roi(stored, degrees, width, height)
    assert on_screen is not None
    shown_w, shown_h = (height, width) if degrees % 180 else (width, height)
    back = unrotate_roi(on_screen, degrees, shown_w, shown_h)
    assert back is not None
    assert back.points == stored.points


def _spread(flags: np.ndarray) -> np.ndarray:
    """``flags`` widened by one pixel in every direction (a 3x3 dilation, numpy only)."""
    padded = np.pad(flags, 1, constant_values=False)
    height, width = flags.shape
    out = np.zeros(flags.shape, bool)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            out |= padded[dy : dy + height, dx : dx + width]
    return out


def _edge_band(mask: np.ndarray) -> np.ndarray:
    """The region's rasterized outline, widened by a pixel on each side."""
    differs = np.zeros(mask.shape, bool)
    differs[:-1, :] |= mask[:-1, :] != mask[1:, :]
    differs[1:, :] |= mask[:-1, :] != mask[1:, :]
    differs[:, :-1] |= mask[:, :-1] != mask[:, 1:]
    differs[:, 1:] |= mask[:, :-1] != mask[:, 1:]
    return _spread(differs)


def test_a_turned_region_crops_exactly_the_same_pixels() -> None:
    """The crop a matcher reads must not depend on which way up the photograph is.

    Two off-by-ones used to compound here — ``height - 1 - y`` for a vertex, which is the map for a
    pixel *index*, and a bounding box that floored both ends — sliding the crop two pixels per
    quarter turn. On a band-passed pattern that changed 30-75% of the pixels and flipped about 40%
    of the keypoints, so turning a photograph moved its identification scores and its shortlist.
    """
    rng = np.random.default_rng(7)
    for _ in range(20):
        height, width = int(rng.integers(60, 140)), int(rng.integers(60, 140))
        image = rng.integers(0, 256, (height, width), np.uint8)
        roi = ROI(
            kind=ROIKind.POLYGON,
            points=tuple(
                (float(rng.uniform(12, width - 12)), float(rng.uniform(12, height - 12)))
                for _ in range(int(rng.integers(3, 8)))
            ),
        )
        upright, upright_mask = crop_to_roi(image, roi, 6)
        assert upright_mask is not None
        for degrees in (90, 180, 270):
            turned_image, turned_roi = oriented(image, roi, degrees)
            assert turned_roi is not None
            crop, mask = crop_to_roi(turned_image, turned_roi, 6)
            wanted = np.rot90(upright, -(degrees // 90))
            assert crop.shape == wanted.shape
            assert (crop == wanted).all()  # exactly, not nearly: it is integer slicing either way
            # The mask is re-rasterized from turned vertices, so it may disagree along the region's
            # own outline — but nowhere inside it, and the crop above is what the matcher reads.
            wanted_mask = np.rot90(upright_mask, -(degrees // 90))
            assert mask is not None
            assert not (mask != wanted_mask)[~_edge_band(wanted_mask)].any()
