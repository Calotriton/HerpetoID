"""Image orientation: the quarter-turns a researcher applied, and what they do to a marked region.

An animal photographed head-down and one photographed head-up are the same animal, but laid side by
side for comparison they are hard to read. The Observations tab lets the orientation be corrected;
this module is what makes the correction *stick*. The turn is stored on the image record, and every
view that loads the photograph — the editor, the identification panels, the match evidence — applies
it here, together with the matching transform of the marked region, so the region never drifts off
the animal it was drawn around.

The bundle stays canonical: the file on disk is never rewritten, and the ROI is stored in the
coordinates of that file. Rotation is applied on the way *out*, so a consumer that has not been
taught about it still gets a consistent (image, region) pair — just an unrotated one.

Qt-free and pure; angles are clockwise degrees, snapped to a quarter turn.
"""

from __future__ import annotations

import numpy as np

from herpetoid.api import ROI, ROIKind
from herpetoid.domain import Image

from .ports import ImageStore

#: The rotations an image can carry, in clockwise degrees.
QUARTER_TURNS = (0, 90, 180, 270)


def normalize_rotation(degrees: int) -> int:
    """Snap any angle to one of :data:`QUARTER_TURNS` (clockwise, so -90 becomes 270)."""
    return round(degrees / 90) % 4 * 90


def rotate_image(image: np.ndarray, degrees: int) -> np.ndarray:
    """``image`` turned clockwise. ``numpy`` turns anticlockwise, hence the negative count."""
    turns = normalize_rotation(degrees) // 90
    if turns == 0:
        return np.asarray(image)
    return np.ascontiguousarray(np.rot90(np.asarray(image), -turns))


def rotate_point(
    x: float, y: float, width: int, height: int, degrees: int
) -> tuple[float, float]:
    """Where ``(x, y)`` of a ``width`` by ``height`` image lands once that image is turned.

    These are *places on the image plane*, not pixel indices: a drawn vertex sits between pixels,
    and the far edge of the frame is at ``height``, not ``height - 1``. A clockwise quarter turn
    therefore sends ``y`` to ``height - y``.

    The distinction is not pedantry. ``height - 1 - y`` is the right map for a pixel index and the
    wrong one for a vertex, and it moved every hand-drawn region a pixel per quarter turn. Together
    with a bounding box that floored both ends (:meth:`herpetoid.api.ROI.bounding_box`) that slid
    the crop handed to a matcher by two pixels — enough, on a band-passed pattern, to change 30-75%
    of its pixels, flip ~40% of its keypoints, and move identification scores and shortlists.
    """
    for _ in range(normalize_rotation(degrees) // 90):
        x, y, width, height = height - y, x, height, width
    return x, y


def rotate_roi(roi: ROI | None, degrees: int, width: int, height: int) -> ROI | None:
    """A ROI mapped onto the turned image. ``width``/``height`` are the size *before* the turn."""
    turns = normalize_rotation(degrees)
    if roi is None or turns == 0 or roi.kind is ROIKind.FULL_IMAGE:
        return roi
    return ROI(
        kind=roi.kind,
        points=tuple(rotate_point(x, y, width, height, turns) for x, y in roi.points),
        mask=rotate_image(roi.mask, turns) if roi.mask is not None else None,
        label=roi.label,
    )


def unrotate_roi(roi: ROI | None, degrees: int, width: int, height: int) -> ROI | None:
    """The inverse of :func:`rotate_roi`: a region drawn on screen, back in the file's coordinates.

    ``width``/``height`` are the size of the image *as displayed* (already turned). Turning by
    ``degrees`` and then back is exact, not approximate — the four quarter turns are a group.
    """
    return rotate_roi(roi, -normalize_rotation(degrees), width, height)


def oriented(
    image: np.ndarray, roi: ROI | None, degrees: int
) -> tuple[np.ndarray, ROI | None]:
    """An image and its region, both turned by ``degrees`` — the pair as the researcher set it up."""
    array = np.asarray(image)
    turns = normalize_rotation(degrees)
    if turns == 0:
        return array, roi
    height, width = array.shape[:2]
    return rotate_image(array, turns), rotate_roi(roi, turns, width, height)


def load_oriented(
    store: ImageStore, image: Image, roi: ROI | None = None
) -> tuple[np.ndarray, ROI | None]:
    """Load ``image`` from the bundle already turned, with ``roi`` mapped to match.

    The single door every viewer should come through, so no screen can show a photograph one way up
    and another screen the other.
    """
    return oriented(store.load(image.rel_path), roi, image.rotation)
