"""Image-domain value objects shared by species modules and algorithms.

* :class:`ROISpec` — a *declarative* description of the region a species expects (drives the GUI tool).
* :class:`ROI` — a *concrete* region on a specific image.
* :class:`Sample` — the standardized preprocessing output; the seam an algorithm consumes. An algorithm
  sees only a ``Sample`` and never knows which species produced it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .enums import ROIKind


@dataclass(frozen=True, slots=True)
class ROISpec:
    """Declarative description of the region a species module expects the user to mark."""

    kind: ROIKind = ROIKind.RECTANGLE
    interactive: bool = True  # the user draws / adjusts the ROI in the GUI
    guidance: str = ""  # instruction text shown next to the ROI tool
    allow_auto_suggest: bool = False  # the module may auto-propose an ROI via select_roi()


@dataclass(slots=True)
class ROI:
    """A concrete region of interest on an image, in pixel coordinates.

    Geometry interpretation depends on ``kind``:

    * ``RECTANGLE`` — ``points`` holds two opposite corners ``[(x0, y0), (x1, y1)]``.
    * ``POLYGON`` / ``LANDMARKS`` — ``points`` holds the vertices / landmarks.
    * ``ELLIPSE`` — ``points`` holds the bounding-box corners.
    * ``MASK`` — ``mask`` holds a boolean/uint8 array the size of the image.
    * ``FULL_IMAGE`` — the whole image (no geometry needed).
    """

    kind: ROIKind
    points: tuple[tuple[float, float], ...] = ()
    mask: np.ndarray | None = None
    label: str | None = None

    @classmethod
    def full_image(cls) -> ROI:
        return cls(kind=ROIKind.FULL_IMAGE)

    @classmethod
    def rectangle(cls, x: float, y: float, w: float, h: float) -> ROI:
        return cls(kind=ROIKind.RECTANGLE, points=((x, y), (x + w, y + h)))

    def bounding_box(self) -> tuple[int, int, int, int] | None:
        """Integer box ``(x, y, w, h)`` covering every pixel the region touches — ``None`` if full.

        The minimum is floored and the maximum **ceiled**. Flooring both ends drops the region's
        last partial pixel, and because the floor of a mirrored coordinate is not the mirror of its
        floor, it also makes the box depend on which way up the photograph is — which slid the crop
        a matcher sees. See :func:`herpetoid.application.orientation.rotate_point`.
        """
        if self.kind is ROIKind.FULL_IMAGE:
            return None
        if self.mask is not None and not self.points:
            mask_ys, mask_xs = np.nonzero(self.mask)
            if mask_xs.size == 0:
                return None
            x0, x1 = int(mask_xs.min()), int(mask_xs.max())
            y0, y1 = int(mask_ys.min()), int(mask_ys.max())
            return (x0, y0, x1 - x0 + 1, y1 - y0 + 1)
        if not self.points:
            return None
        xs = [p[0] for p in self.points]
        ys = [p[1] for p in self.points]
        x0, y0 = math.floor(min(xs)), math.floor(min(ys))
        x1, y1 = math.ceil(max(xs)), math.ceil(max(ys))
        return (x0, y0, x1 - x0, y1 - y0)


@dataclass(slots=True)
class Sample:
    """Standardized, normalized preprocessing output consumed by algorithms (species-agnostic)."""

    image: np.ndarray  # normalized pattern image, (H, W) grayscale or (H, W, C)
    roi_mask: np.ndarray | None = None  # mask of the pattern region within ``image``
    color_space: str = "gray"  # 'gray' | 'rgb' | 'lab' | ...
    keypoints: np.ndarray | None = None  # optional (N, 2) landmarks supplied by the module
    pixel_scale: float | None = None  # millimetres per pixel, if calibrated
    meta: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.image.ndim not in (2, 3):
            raise ValueError(f"Sample.image must be 2-D or 3-D, got shape {self.image.shape!r}")
        if self.roi_mask is not None and self.roi_mask.shape[:2] != self.image.shape[:2]:
            raise ValueError("Sample.roi_mask must match the image height and width")

    @property
    def is_grayscale(self) -> bool:
        return self.image.ndim == 2

    @property
    def size(self) -> tuple[int, int]:
        """Image ``(width, height)`` in pixels."""
        h, w = self.image.shape[:2]
        return (int(w), int(h))
