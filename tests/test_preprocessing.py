"""Tests for the shared, OpenCV-backed preprocessing helpers species modules build on.

These are the pieces both first-party modules now share: isolate the marked region, pick the channel
the pattern lives in, and remove the illumination by spatial frequency.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from herpetoid.api import ROI, ROIKind
from herpetoid.api.preprocessing import (
    band_pass,
    crop_to_roi,
    is_color,
    luminance,
    otsu,
    reference_length,
    roi_mask,
    scale_to_u8,
    stretch_percentile,
    yellowness,
)


def _blobs(size: int = 240, radius: int = 10, seed: int = 0) -> np.ndarray:
    """A grey field with darker blobs — a stand-in for any spotted pattern."""
    rng = np.random.default_rng(seed)
    image = np.full((size, size), 170, np.uint8)
    for _ in range(24):
        centre = (int(rng.integers(radius, size - radius)), int(rng.integers(radius, size - radius)))
        cv2.circle(image, centre, radius, 60, -1)
    return image


def test_roi_mask_covers_polygon_rectangle_and_full_image() -> None:
    image = np.zeros((40, 60, 3), np.uint8)
    polygon = ROI(kind=ROIKind.POLYGON, points=((5.0, 5.0), (30.0, 5.0), (30.0, 25.0), (5.0, 25.0)))
    mask = roi_mask(image, polygon)
    assert mask is not None and mask[15, 15] == 255 and mask[35, 55] == 0

    rectangle = roi_mask(image, ROI.rectangle(10, 10, 20, 10))
    assert rectangle is not None and rectangle[15, 15] == 255 and rectangle[5, 5] == 0

    assert roi_mask(image, ROI.full_image()) is None


def test_crop_to_roi_widens_by_the_margin_and_clamps_to_the_image() -> None:
    image = np.zeros((200, 300, 3), np.uint8)
    roi = ROI.rectangle(100, 80, 40, 30)

    flush, flush_mask = crop_to_roi(image, roi, margin=0)
    assert flush.shape[:2] == (30, 40)
    assert flush_mask is not None and flush_mask.shape[:2] == flush.shape[:2]

    padded, padded_mask = crop_to_roi(image, roi, margin=25)
    assert padded.shape[:2] == (80, 90)
    assert padded_mask is not None and padded_mask.shape[:2] == padded.shape[:2]

    # A margin larger than the surrounding image clamps instead of going out of bounds.
    clamped, _ = crop_to_roi(image, roi, margin=10_000)
    assert clamped.shape[:2] == image.shape[:2]
    # A full-image ROI has nothing to crop to.
    whole, whole_mask = crop_to_roi(image, ROI.full_image())
    assert whole.shape == image.shape and whole_mask is None


def test_channels_pick_out_lightness_and_yellowness() -> None:
    yellow = np.full((8, 8, 3), (236, 196, 40), np.uint8)
    black = np.full((8, 8, 3), (28, 24, 22), np.uint8)
    white = np.full((8, 8, 3), (250, 250, 250), np.uint8)

    # Yellowness separates yellow from both black and a specular highlight; lightness does not
    # separate yellow from white — which is the whole reason the two modules differ.
    assert yellowness(yellow).mean() > yellowness(black).mean() + 40
    assert yellowness(yellow).mean() > yellowness(white).mean() + 40
    assert luminance(white).mean() > luminance(black).mean()
    assert abs(luminance(yellow).mean() - luminance(white).mean()) < abs(
        yellowness(yellow).mean() - yellowness(white).mean()
    )

    grey = np.full((8, 8), 120, np.uint8)  # monochrome input passes through both channels
    assert luminance(grey).mean() == pytest.approx(120.0)
    assert yellowness(grey).mean() == pytest.approx(120.0)
    assert is_color(yellow) and not is_color(grey)


def test_stretch_percentile_uses_only_masked_pixels() -> None:
    values = np.zeros((50, 50), np.float32)
    values[10:40, 10:40] = np.linspace(80, 120, 30 * 30).reshape(30, 30)
    values[0:5, 0:5] = 5000.0  # a bright intruder outside the region
    mask = np.zeros((50, 50), np.uint8)
    mask[10:40, 10:40] = 255

    stretched = stretch_percentile(values, mask)
    inside = stretched[mask > 0]
    assert inside.min() == 0 and inside.max() == 255  # the region spans the full range
    assert stretched[0, 0] == 255  # the intruder is clipped, not used to set the scale


def test_reference_length_follows_the_masked_region() -> None:
    values = np.zeros((400, 600), np.float32)
    mask = np.zeros((400, 600), np.uint8)
    mask[100:300, 50:550] = 255  # 200 tall, 500 wide
    assert reference_length(values, mask) == pytest.approx(200.0)
    assert reference_length(values, None) == pytest.approx(400.0)


def test_band_pass_removes_an_illumination_gradient() -> None:
    """The point of the band-pass: a slow light field must not survive it."""
    pattern = _blobs()
    gradient = np.linspace(0.35, 1.3, pattern.shape[1], dtype=np.float32)[None, :]
    lit = np.clip(pattern.astype(np.float32) * gradient, 0, 255)

    even = band_pass(pattern.astype(np.float32))
    uneven = band_pass(lit)
    # Band-passing the lit and the evenly lit capture gives nearly the same pattern image…
    assert float(np.mean(np.abs(even.astype(float) - uneven.astype(float)))) < 12.0
    # …whereas a global histogram equalization keeps the gradient's fingerprint.
    equalized_even = cv2.equalizeHist(pattern)
    equalized_uneven = cv2.equalizeHist(lit.astype(np.uint8))
    assert float(
        np.mean(np.abs(equalized_even.astype(float) - equalized_uneven.astype(float)))
    ) > float(np.mean(np.abs(even.astype(float) - uneven.astype(float))))


def test_band_pass_widths_track_the_region_not_the_pixel_count() -> None:
    """ROI-relative widths are what make a module behave the same at any magnification."""
    pattern = _blobs(size=240, radius=10)
    zoomed = cv2.resize(pattern, (480, 480), interpolation=cv2.INTER_LINEAR)

    relative_small = band_pass(pattern.astype(np.float32))
    relative_large = band_pass(zoomed.astype(np.float32))
    # Bring them back to a common size to compare the extracted patterns.
    rescaled = cv2.resize(relative_large, (240, 240), interpolation=cv2.INTER_AREA)
    relative_difference = float(np.mean(np.abs(relative_small.astype(float) - rescaled.astype(float))))

    # Pinning `scale` reproduces fixed-pixel widths: the same filter at twice the magnification.
    fixed_large = band_pass(zoomed.astype(np.float32), scale=240.0)
    fixed_rescaled = cv2.resize(fixed_large, (240, 240), interpolation=cv2.INTER_AREA)
    fixed_difference = float(np.mean(np.abs(relative_small.astype(float) - fixed_rescaled.astype(float))))

    assert relative_difference < fixed_difference, (
        "ROI-relative widths should survive a magnification change better than fixed ones"
    )


def test_band_pass_rejects_an_inverted_band() -> None:
    with pytest.raises(ValueError):
        band_pass(np.zeros((20, 20), np.float32), low_fraction=0.2, high_fraction=0.1)


def test_otsu_foreground_is_strictly_above_the_threshold() -> None:
    """On a flat-toned image OpenCV returns the lowest of several tying thresholds, so a `>=` test
    would hand back the darker class too."""
    pattern = np.full((40, 40), 56, np.uint8)
    pattern[10:20, 10:20] = 255
    binary = otsu(pattern)
    assert binary[15, 15] == 255
    assert binary[0, 0] == 0
    assert set(np.unique(binary)) == {0, 255}


def test_scale_to_u8_handles_a_flat_array() -> None:
    assert scale_to_u8(np.full((4, 4), 7.0)).max() == 0
    assert scale_to_u8(np.array([[0.0, 0.5], [1.0, 0.25]])).max() == 255
