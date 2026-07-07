"""Tests for feature/match value objects and the algorithm base-class defaults."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from herpetoid import api


class _Algo(api.IdentificationAlgorithm):
    @classmethod
    def descriptor(cls) -> api.AlgorithmDescriptor:
        return api.AlgorithmDescriptor("t", "T", "1", api.AlgorithmFamily.KEYPOINT)

    def extract_features(self, sample: api.Sample) -> api.FeatureSet:
        return api.FeatureSet("t", api.AlgorithmFamily.KEYPOINT, np.zeros((3, 4)))

    def compare(self, query: api.FeatureSet, target: api.FeatureSet) -> api.ComparisonResult:
        index = float(target.ref.split(":")[1]) if target.ref else 0.0
        return api.ComparisonResult(score=index, normalized_score=1.0 / (1.0 + index))


def test_featureset_count() -> None:
    assert api.FeatureSet("t", api.AlgorithmFamily.EMBEDDING, np.zeros(8)).count == 1
    assert api.FeatureSet("t", api.AlgorithmFamily.KEYPOINT, np.zeros((5, 8))).count == 5


def test_save_load_roundtrip(tmp_path: Path) -> None:
    algo = _Algo()
    features = api.FeatureSet(
        "t",
        api.AlgorithmFamily.KEYPOINT,
        np.arange(12, dtype=np.float32).reshape(3, 4),
        keypoints=np.ones((3, 2)),
        ref="img:7",
        meta={"k": 1},
    )
    path = tmp_path / "features.npz"
    algo.save_features(features, path)
    loaded = algo.load_features(path)
    assert np.array_equal(features.descriptors, loaded.descriptors)
    assert np.array_equal(features.keypoints, loaded.keypoints)
    assert loaded.ref == "img:7"
    assert loaded.meta == {"k": 1}
    assert loaded.algorithm_id == "t"
    assert loaded.kind is api.AlgorithmFamily.KEYPOINT


def test_rank_orders_by_normalized_score() -> None:
    algo = _Algo()
    query = api.FeatureSet("t", api.AlgorithmFamily.KEYPOINT, np.zeros((1, 4)))
    candidates = [
        api.FeatureSet("t", api.AlgorithmFamily.KEYPOINT, np.zeros((1, 4)), ref=f"c:{i}")
        for i in (3, 1, 2)
    ]
    ranked = algo.rank(query, candidates)
    assert [c.target_ref for c in ranked.candidates] == ["c:1", "c:2", "c:3"]
    assert [c.rank for c in ranked.candidates] == [1, 2, 3]
