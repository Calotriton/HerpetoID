"""Tests for imaging value objects (Sample, ROI) and the SpeciesProfile manifest."""

from __future__ import annotations

import numpy as np
import pytest

from herpetoid import api


def test_sample_shape_validation() -> None:
    sample = api.Sample(image=np.zeros((4, 5), np.uint8))
    assert sample.is_grayscale
    assert sample.size == (5, 4)
    with pytest.raises(ValueError):
        api.Sample(image=np.zeros((4,), np.uint8))  # 1-D not allowed
    with pytest.raises(ValueError):
        api.Sample(image=np.zeros((4, 5)), roi_mask=np.zeros((3, 3)))  # mask mismatch


def test_roi_bounding_box() -> None:
    assert api.ROI.rectangle(2, 3, 10, 20).bounding_box() == (2, 3, 10, 20)
    assert api.ROI.full_image().bounding_box() is None
    mask = np.zeros((10, 10), dtype=bool)
    mask[2:5, 3:7] = True
    assert api.ROI(kind=api.ROIKind.MASK, mask=mask).bounding_box() == (3, 2, 4, 3)


def test_profile_requires_name() -> None:
    with pytest.raises(ValueError):
        api.SpeciesProfile(scientific_name="")


def test_derived_statistic_validation() -> None:
    with pytest.raises(ValueError):
        api.DerivedStatistic("x", "X", api.StatisticKind.AGGREGATE)  # missing source_field
    with pytest.raises(ValueError):
        api.DerivedStatistic("y", "Y", api.StatisticKind.DERIVED)  # missing compute callable

    aggregate = api.DerivedStatistic(
        "mean_svl", "Mean SVL", api.StatisticKind.AGGREGATE, source_field="svl"
    )
    assert aggregate.source_field == "svl"

    derived = api.DerivedStatistic(
        "bci", "Body condition", api.StatisticKind.DERIVED, compute=lambda values: 1.0
    )
    assert derived.compute is not None and derived.compute({}) == 1.0


def test_algorithm_compatibility_accepts_family() -> None:
    compat = api.AlgorithmCompatibility(families=(api.AlgorithmFamily.KEYPOINT,))
    assert compat.accepts_family(api.AlgorithmFamily.KEYPOINT)
    assert not compat.accepts_family(api.AlgorithmFamily.EMBEDDING)
