"""Tests for rank fusion, the identification service, and the synchronous task runner."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from herpetoid import api
from herpetoid.application.fusion import reciprocal_rank_fusion, weighted_score_fusion
from herpetoid.application.identification import IdentificationService
from herpetoid.application.ports import SynchronousTaskRunner
from herpetoid.plugins.algorithms.orb import OrbAlgorithm
from herpetoid.plugins.species.calotriton_asper import CalotritonAsperModule


@pytest.fixture(autouse=True)
def _deterministic_cv() -> None:
    cv2.setRNGSeed(12345)


def _ranking(algorithm_id: str, refs: list[str]) -> api.RankedResult:
    candidates = tuple(
        api.MatchCandidate(ref, 1.0 / (i + 1), 1.0 / (i + 1), i + 1) for i, ref in enumerate(refs)
    )
    return api.RankedResult(algorithm_id, candidates)


def _spot_pattern(seed: int, size: int = 256, count: int = 45) -> np.ndarray:
    rng = np.random.default_rng(seed)
    image = np.full((size, size), 255, dtype=np.uint8)
    for _ in range(count):
        cx, cy = rng.integers(20, size - 20, size=2)
        ax, ay = rng.integers(5, 15, size=2)
        cv2.ellipse(
            image, (int(cx), int(cy)), (int(ax), int(ay)), int(rng.integers(0, 180)), 0, 360, 0, -1
        )
    return image


def _rotate(image: np.ndarray, degrees: float) -> np.ndarray:
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
    return cv2.warpAffine(image, matrix, (w, h), borderValue=255)


def test_reciprocal_rank_fusion() -> None:
    a = _ranking("a", ["x", "y", "z"])
    b = _ranking("b", ["y", "x", "w"])
    fused = reciprocal_rank_fusion([a, b], top_k=3)
    assert fused.algorithm_id == "fused"
    # x and y tie (top), as do z and w (third); ties break by ref, so "w" precedes "z".
    assert [c.target_ref for c in fused.candidates] == ["x", "y", "w"]


def test_weighted_score_fusion_respects_weights() -> None:
    a = _ranking("a", ["x", "y"])
    b = _ranking("b", ["y", "x"])
    equal = weighted_score_fusion([a, b], top_k=2)
    assert [c.target_ref for c in equal.candidates] == ["x", "y"]  # tie broken by ref
    weighted = weighted_score_fusion([a, b], top_k=2, weights={"a": 1.0, "b": 3.0})
    assert weighted.candidates[0].target_ref == "y"


def test_synchronous_task_runner() -> None:
    runner = SynchronousTaskRunner()
    captured: list[int] = []
    runner.submit(lambda: 42, on_done=captured.append)
    assert captured == [42]


class _FakeAlgo(api.IdentificationAlgorithm):
    @classmethod
    def descriptor(cls) -> api.AlgorithmDescriptor:
        return api.AlgorithmDescriptor("fake", "F", "1", api.AlgorithmFamily.EMBEDDING)

    def extract_features(self, sample: api.Sample) -> api.FeatureSet:
        return api.FeatureSet(
            "fake", api.AlgorithmFamily.EMBEDDING, sample.image.astype(float).ravel()
        )

    def compare(self, query: api.FeatureSet, target: api.FeatureSet) -> api.ComparisonResult:
        a, b = query.descriptors.ravel(), target.descriptors.ravel()
        n = min(a.size, b.size)
        distance = float(np.linalg.norm(a[:n] - b[:n]))
        return api.ComparisonResult(score=-distance, normalized_score=1.0 / (1.0 + distance))


def test_identification_service_single_algorithm() -> None:
    algo = _FakeAlgo()
    query = api.Sample(image=np.zeros((4, 4), np.uint8))
    same = algo.extract_features(api.Sample(image=np.zeros((4, 4), np.uint8)))
    same.ref = "match"
    diff = algo.extract_features(api.Sample(image=np.full((4, 4), 200, np.uint8)))
    diff.ref = "nomatch"

    outcome = IdentificationService().identify(
        query_sample=query, algorithms=[algo], catalog_features={"fake": [diff, same]}, top_k=2
    )
    assert outcome.per_algorithm["fake"].candidates[0].target_ref == "match"
    assert outcome.fused.candidates[0].target_ref == "match"
    assert outcome.fused.algorithm_id == "fused"


def test_identification_service_requires_algorithm() -> None:
    with pytest.raises(ValueError):
        IdentificationService().identify(
            query_sample=api.Sample(image=np.zeros((4, 4), np.uint8)),
            algorithms=[],
            catalog_features={},
        )


def test_identification_service_with_orb() -> None:
    module = CalotritonAsperModule(config={"denoise": False})
    algo = OrbAlgorithm()
    roi = api.ROI.full_image()
    query_image = _spot_pattern(1)
    query_sample = module.preprocess(query_image, roi)

    same = algo.extract_features(module.preprocess(_rotate(query_image, 9), roi))
    same.ref = "ind-1"
    other = algo.extract_features(module.preprocess(_spot_pattern(321), roi))
    other.ref = "ind-2"

    outcome = IdentificationService().identify(
        query_sample=query_sample,
        algorithms=[algo],
        catalog_features={"orb": [same, other]},
        top_k=2,
    )
    assert outcome.fused.candidates[0].target_ref == "ind-1"
