"""Tests for the first-party plugins (ORB algorithm + Calotriton asper module).

Includes the reusable conformance suites run against the real plugins, and an end-to-end
identification pipeline that must rank the same individual above different ones.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from herpetoid import api
from herpetoid.application.registry import PluginRegistry
from herpetoid.infrastructure.plugin_discovery import discover_entry_points
from herpetoid.plugins.algorithms.orb import OrbAlgorithm
from herpetoid.plugins.species.calotriton_asper import CalotritonAsperModule
from herpetoid.testing import AlgorithmContract, SpeciesModuleContract


@pytest.fixture(autouse=True)
def _deterministic_cv() -> None:
    cv2.setRNGSeed(12345)


def _spot_pattern(seed: int, size: int = 256, count: int = 45) -> np.ndarray:
    """A synthetic 'ventral pattern': dark ellipses (spots) on a pale ground."""
    rng = np.random.default_rng(seed)
    image = np.full((size, size), 255, dtype=np.uint8)
    for _ in range(count):
        cx, cy = rng.integers(20, size - 20, size=2)
        ax, ay = rng.integers(5, 15, size=2)
        angle = int(rng.integers(0, 180))
        cv2.ellipse(image, (int(cx), int(cy)), (int(ax), int(ay)), angle, 0, 360, 0, -1)
    return image


def _rotate(image: np.ndarray, degrees: float) -> np.ndarray:
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
    return cv2.warpAffine(image, matrix, (w, h), borderValue=255)


class TestOrbConformance(AlgorithmContract):
    def make_algorithm(self) -> api.IdentificationAlgorithm:
        return OrbAlgorithm()


class TestCalotritonConformance(SpeciesModuleContract):
    def make_module(self) -> api.SpeciesModule:
        return CalotritonAsperModule()


def test_calotriton_profile() -> None:
    profile = CalotritonAsperModule().define_species_profile()
    assert profile.scientific_name == "Calotriton asper"
    assert profile.pattern_region == "ventral"
    assert {f.key for f in profile.measurements} == {"svl", "weight", "sex", "life_stage"}
    assert api.AlgorithmFamily.KEYPOINT in profile.compatible_algorithms.families
    assert {s.key for s in profile.derived_statistics} >= {"mean_svl", "sex_ratio", "svl_growth"}


def test_preprocess_produces_grayscale_sample() -> None:
    sample = CalotritonAsperModule().preprocess(_spot_pattern(1), api.ROI.full_image())
    assert sample.is_grayscale
    assert sample.image.dtype == np.uint8


def test_identification_pipeline_discriminates() -> None:
    module = CalotritonAsperModule(config={"denoise": False})
    algo = OrbAlgorithm()
    roi = api.ROI.full_image()

    query_image = _spot_pattern(1)
    query = algo.extract_features(module.preprocess(query_image, roi))
    assert query.descriptors.shape[0] > 10  # features were found

    # same individual, rotated -> should match strongly
    same = algo.extract_features(module.preprocess(_rotate(query_image, 12), roi))
    same_result = algo.compare(query, same)

    # a different individual -> weaker match
    other = algo.extract_features(module.preprocess(_spot_pattern(777), roi))
    other_result = algo.compare(query, other)

    assert same_result.inliers > other_result.inliers
    assert same_result.normalized_score > other_result.normalized_score


def test_rank_puts_same_individual_first() -> None:
    module = CalotritonAsperModule(config={"denoise": False})
    algo = OrbAlgorithm()
    roi = api.ROI.full_image()

    query_image = _spot_pattern(1)
    query = algo.extract_features(module.preprocess(query_image, roi))

    same = algo.extract_features(module.preprocess(_rotate(query_image, 8), roi))
    same.ref = "same-individual"
    candidates = [same]
    for i in range(3):
        other = algo.extract_features(module.preprocess(_spot_pattern(100 + i), roi))
        other.ref = f"other-{i}"
        candidates.append(other)

    ranked = algo.rank(query, candidates)
    assert ranked.candidates[0].target_ref == "same-individual"


def test_first_party_plugins_discoverable_via_entry_points() -> None:
    registry = PluginRegistry()
    discover_entry_points(registry)
    assert registry.algorithm("orb") is not None
    assert registry.module("calotriton_asper") is not None
    # capability matching wires the module to the ORB algorithm
    module = registry.create_module("calotriton_asper")
    compatible = registry.algorithms_for(module.compatible_algorithms())
    assert "orb" in {record.descriptor.algorithm_id for record in compatible}
