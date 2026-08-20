"""Optional image-preparation helpers for species modules (OpenCV-backed).

Deliberately **not** re-exported from :mod:`herpetoid.api`: importing the SDK stays pure Python +
NumPy (see ``tests/test_api_qtfree.py``), and a module opts into these helpers explicitly::

    from herpetoid.api.preprocessing import band_pass, crop_to_roi, yellowness

They exist because every species module faces the same three problems — isolate the marked region,
pick the channel the pattern actually lives in, and get rid of the illumination — and the answers
differ only in **which channel**, never in how.

*Which channel* is the species question. A fire salamander's pattern is yellow on neutral black, so it
lives in chromaticity (:func:`yellowness`); a brook newt's is dark spots on a pale belly, so it lives
in lightness (:func:`luminance`) and no colour transform can rescue it.

*How to remove the illumination* is the same answer for both: :func:`band_pass`. Lighting varies
slowly across a frame, the pattern does not, so they separate by spatial frequency. Histogram
equalization does not do this — it is a global remap, so a torch beam or a shadow on one side still
rewrites the whole image.
"""

from __future__ import annotations

import cv2
import numpy as np

from .enums import ROIKind
from .imaging import ROI

#: Keypoint detectors ignore a border (ORB's default ``edgeThreshold`` is 31 px, and its pyramid
#: makes the effective band larger), so cropping flush to a region throws away the pattern's outermost
#: marks. Kept in pixels, not as a fraction: the detector's blind border is a fixed pixel count.
DEFAULT_ROI_MARGIN = 64


def scale_to_u8(array: np.ndarray) -> np.ndarray:
    """Linearly rescale any numeric array to the full ``uint8`` range."""
    values = array.astype(np.float64)
    low, high = float(values.min()), float(values.max())
    if high <= low:
        return np.zeros(values.shape, dtype=np.uint8)
    return ((values - low) / (high - low) * 255.0).astype(np.uint8)


def roi_mask(image: np.ndarray, roi: ROI) -> np.ndarray | None:
    """The ROI as a ``uint8`` mask over ``image``, or ``None`` when it covers the whole frame."""
    if roi.kind is ROIKind.POLYGON and roi.points:
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        points = np.array(roi.points, dtype=np.int32).reshape(-1, 1, 2)
        cv2.fillPoly(mask, [points], 255)
        return mask
    if roi.mask is not None:
        return (np.asarray(roi.mask) > 0).astype(np.uint8) * 255
    box = roi.bounding_box()
    if box is not None:
        mask = np.zeros(image.shape[:2], dtype=np.uint8)
        x, y, w, h = box
        mask[max(0, y) : y + h, max(0, x) : x + w] = 255
        return mask
    return None


def crop_to_roi(
    image: np.ndarray, roi: ROI, margin: int = DEFAULT_ROI_MARGIN
) -> tuple[np.ndarray, np.ndarray | None]:
    """The ROI's bounding box widened by ``margin`` pixels, with its mask.

    The margin is not cosmetic: see :data:`DEFAULT_ROI_MARGIN`. The mask is returned uncropped-to-match
    so callers can pass it straight to a detector.
    """
    mask = roi_mask(image, roi)
    box = roi.bounding_box()
    if box is None:
        return image, mask
    x, y, w, h = box
    margin = max(0, margin)
    x0, y0 = max(0, x - margin), max(0, y - margin)
    x1 = min(image.shape[1], x + w + margin)
    y1 = min(image.shape[0], y + h + margin)
    if x1 <= x0 or y1 <= y0:
        return image, mask
    return image[y0:y1, x0:x1], (mask[y0:y1, x0:x1] if mask is not None else None)


def luminance(image: np.ndarray) -> np.ndarray:
    """Lightness as ``float32``. A 2-D input is already a lightness image and passes through."""
    array = np.asarray(image)
    if array.ndim == 2:
        return array.astype(np.float32)
    rgb = array[:, :, :3]
    if rgb.dtype != np.uint8:
        rgb = scale_to_u8(rgb)
    return cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2GRAY).astype(np.float32)


def yellowness(image: np.ndarray) -> np.ndarray:
    """The blue→yellow axis (CIE Lab ``b*``) as ``float32``: high on yellow, low on blue.

    Neutral tones — black skin, grey rock, a white specular highlight — all sit near the middle, which
    is what makes this channel indifferent to how the animal was lit. A 2-D input carries no colour;
    its intensity is returned so a monochrome capture still produces something usable.
    """
    array = np.asarray(image)
    if array.ndim == 2:
        return array.astype(np.float32)
    rgb = array[:, :, :3]  # an alpha channel carries no pattern information
    if rgb.dtype != np.uint8:
        rgb = scale_to_u8(rgb)
    lab = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2LAB)
    return lab[:, :, 2].astype(np.float32)


def is_color(image: np.ndarray) -> bool:
    """Whether ``image`` carries colour a chromatic channel could read."""
    return np.asarray(image).ndim == 3


def reference_length(values: np.ndarray, mask: np.ndarray | None) -> float:
    """The pattern's scale reference: the shorter side of the masked region, else of the image.

    Filter widths are expressed as fractions of this, so a species module behaves the same whether the
    animal fills 300 pixels or 3000 — the pattern's marks scale with the region, not with the sensor.
    """
    if mask is not None:
        ys, xs = np.nonzero(mask)
        if xs.size:
            height = float(ys.max() - ys.min() + 1)
            width = float(xs.max() - xs.min() + 1)
            return max(1.0, min(height, width))
    return max(1.0, float(min(values.shape[:2])))


def stretch_percentile(
    values: np.ndarray, mask: np.ndarray | None = None, low: float = 2.0, high: float = 98.0
) -> np.ndarray:
    """Percentile contrast stretch to ``uint8``, with the percentiles taken inside ``mask`` only.

    Restricting the statistics to the region is what makes the result independent of the surroundings:
    the same animal on leaf litter and on wet rock normalizes to the same image.
    """
    inside = values[mask > 0] if mask is not None else values
    if inside.size == 0:
        inside = values
    bounds = np.percentile(inside, (low, high))
    low_value, high_value = float(bounds[0]), float(bounds[1])
    if high_value <= low_value:
        return np.zeros(values.shape, dtype=np.uint8)
    scaled = (values - low_value) / (high_value - low_value)
    return (np.clip(scaled, 0.0, 1.0) * 255.0).astype(np.uint8)


def band_pass(
    values: np.ndarray,
    mask: np.ndarray | None = None,
    *,
    low_fraction: float = 0.01,
    high_fraction: float = 0.06,
    scale: float | None = None,
) -> np.ndarray:
    """Difference of Gaussians on ``values``, returned as a stretched ``uint8`` pattern image.

    Keeps structure between the two widths and discards everything outside it: the slow illumination
    field above, sensor noise below. Both widths are **fractions of the region's shorter side**
    (:func:`reference_length`), so the filter tracks the animal's size in the frame instead of the
    photographer's distance — pass ``scale`` to override the reference.
    """
    if high_fraction <= low_fraction:
        raise ValueError("band_pass: high_fraction must exceed low_fraction")
    reference = reference_length(values, mask) if scale is None else max(1.0, float(scale))
    small = max(0.8, low_fraction * reference)
    large = max(small + 0.8, high_fraction * reference)
    floats = values.astype(np.float32)
    detail = cv2.GaussianBlur(floats, (0, 0), small) - cv2.GaussianBlur(floats, (0, 0), large)
    return stretch_percentile(detail, mask)


def otsu(pattern: np.ndarray, mask: np.ndarray | None = None) -> np.ndarray:
    """Split ``pattern`` in two with Otsu's threshold, computed over ``mask`` pixels only.

    Foreground is ``> threshold`` — strictly, as OpenCV defines it: on a flat-toned image several
    thresholds tie and OpenCV returns the lowest, so ``>=`` would hand back the darker class as well.
    """
    inside = pattern[mask > 0] if mask is not None else pattern.reshape(-1)
    if inside.size == 0:
        inside = pattern.reshape(-1)
    threshold, _ = cv2.threshold(inside, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return ((pattern > float(threshold)) * 255).astype(np.uint8)
