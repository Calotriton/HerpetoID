"""ORB identification algorithm: keypoint matching with geometric verification.

Pipeline: ORB features -> BFMatcher (Hamming) -> Lowe ratio test -> RANSAC homography ->
score derived from inlier count, inlier ratio and homography validity. Species-agnostic: it consumes
only a standardized :class:`~herpetoid.api.Sample`.
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from herpetoid.api import (
    AlgorithmContext,
    AlgorithmDescriptor,
    AlgorithmFamily,
    ComparisonResult,
    FeatureSet,
    IdentificationAlgorithm,
    Overlay,
    Sample,
    ScoreSemantics,
    Visualization,
)

_DEFAULT_CONFIG: dict[str, Any] = {
    "nfeatures": 1000,
    "lowe_ratio": 0.75,
    "ransac_reproj_threshold": 5.0,
    "min_good_matches": 4,
    "confident_inliers": 30,  # inlier count at which the inlier component saturates to 1.0
}

_CONFIG_SCHEMA: dict[str, Any] = {
    "nfeatures": {"type": "int", "label": "ORB features", "min": 100, "max": 10000},
    "lowe_ratio": {"type": "float", "label": "Lowe ratio", "min": 0.5, "max": 0.95},
    "ransac_reproj_threshold": {
        "type": "float",
        "label": "RANSAC reproj (px)",
        "min": 1.0,
        "max": 15.0,
    },
    "min_good_matches": {"type": "int", "label": "Min good matches", "min": 4, "max": 100},
}


def _scale_to_u8(array: np.ndarray) -> np.ndarray:
    values = array.astype(np.float64)
    low, high = float(values.min()), float(values.max())
    if high <= low:
        return np.zeros(values.shape, dtype=np.uint8)
    return ((values - low) / (high - low) * 255.0).astype(np.uint8)


def _to_gray_u8(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image)
    if array.ndim == 3:
        code = cv2.COLOR_RGBA2GRAY if array.shape[2] == 4 else cv2.COLOR_RGB2GRAY
        array = np.asarray(cv2.cvtColor(array, code))
    if array.dtype != np.uint8:
        array = _scale_to_u8(array)
    return np.ascontiguousarray(array)


def _homography_quality(homography: np.ndarray | None) -> float:
    """A [0, 1] measure of homography plausibility (1.0 for a near-similarity transform)."""
    if homography is None:
        return 0.0
    determinant = float(np.linalg.det(homography[:2, :2]))
    if not np.isfinite(determinant) or determinant <= 1e-8:
        return 0.0
    return float(max(0.0, 1.0 - abs(np.log(abs(determinant))) / 4.0))


class OrbAlgorithm(IdentificationAlgorithm):
    """ORB + BFMatcher(Hamming) + Lowe ratio + RANSAC homography."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config: dict[str, Any] = {**_DEFAULT_CONFIG, **(config or {})}
        self._orb: Any = None

    @classmethod
    def descriptor(cls) -> AlgorithmDescriptor:
        return AlgorithmDescriptor(
            algorithm_id="orb",
            name="ORB (keypoint matching)",
            version="1.0",
            family=AlgorithmFamily.KEYPOINT,
            score_semantics=ScoreSemantics.SIMILARITY,
            requires_grayscale=False,
            needs_gpu=False,
            description="ORB features with BFMatcher (Hamming), Lowe ratio test and RANSAC homography.",
            config_schema=_CONFIG_SCHEMA,
            default_config=dict(_DEFAULT_CONFIG),
        )

    def initialize(self, ctx: AlgorithmContext) -> None:
        self._config = {**self._config, **dict(ctx.config)}
        self._orb = None  # rebuilt lazily with the new nfeatures

    def _detector(self) -> Any:
        if self._orb is None:
            n = int(self._config["nfeatures"])
            self._orb = cv2.ORB_create(nfeatures=n)  # type: ignore[attr-defined]
        return self._orb

    def extract_features(self, sample: Sample) -> FeatureSet:
        gray = _to_gray_u8(sample.image)
        mask = None
        if sample.roi_mask is not None:
            mask = (np.asarray(sample.roi_mask) > 0).astype(np.uint8) * 255
        keypoints, descriptors = self._detector().detectAndCompute(gray, mask)
        if descriptors is None:
            descriptors = np.empty((0, 32), dtype=np.uint8)
        if keypoints:
            geometry = np.array(
                [[kp.pt[0], kp.pt[1], kp.size, kp.angle] for kp in keypoints], dtype=np.float32
            )
        else:
            geometry = np.empty((0, 4), dtype=np.float32)
        return FeatureSet(
            algorithm_id="orb",
            kind=AlgorithmFamily.KEYPOINT,
            descriptors=descriptors,
            keypoints=geometry,
        )

    def compare(self, query: FeatureSet, target: FeatureSet) -> ComparisonResult:
        query_desc = np.asarray(query.descriptors)
        target_desc = np.asarray(target.descriptors)
        if query_desc.shape[0] < 2 or target_desc.shape[0] < 2:
            return ComparisonResult(score=0.0, normalized_score=0.0)
        query_kp = query.keypoints
        target_kp = target.keypoints
        if query_kp is None or target_kp is None:
            return ComparisonResult(score=0.0, normalized_score=0.0)

        matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        ratio = float(self._config["lowe_ratio"])
        good = [
            pair[0]
            for pair in matcher.knnMatch(query_desc, target_desc, k=2)
            if len(pair) == 2 and pair[0].distance < ratio * pair[1].distance
        ]
        if len(good) < int(self._config["min_good_matches"]):
            return ComparisonResult(
                score=float(len(good)), normalized_score=0.0, meta={"good_matches": len(good)}
            )

        query_pts = np.array([query_kp[m.queryIdx][:2] for m in good], dtype=np.float32).reshape(
            -1, 1, 2
        )
        target_pts = np.array([target_kp[m.trainIdx][:2] for m in good], dtype=np.float32).reshape(
            -1, 1, 2
        )
        homography, inlier_mask = cv2.findHomography(
            query_pts, target_pts, cv2.RANSAC, float(self._config["ransac_reproj_threshold"])
        )
        inliers = int(inlier_mask.sum()) if inlier_mask is not None else 0
        inlier_ratio = inliers / len(good) if good else 0.0
        quality = _homography_quality(homography)

        confident = float(self._config["confident_inliers"])
        inlier_component = min(1.0, inliers / confident) if confident > 0 else 0.0
        normalized = 0.0 if quality <= 0.0 else float(0.5 * inlier_component + 0.5 * inlier_ratio)

        correspondences = None
        if inlier_mask is not None and inliers > 0:
            flags = inlier_mask.ravel().astype(bool)
            q_flat = query_pts.reshape(-1, 2)[flags]
            t_flat = target_pts.reshape(-1, 2)[flags]
            correspondences = np.hstack([q_flat, t_flat])

        return ComparisonResult(
            score=float(inliers),
            normalized_score=normalized,
            inliers=inliers,
            inlier_ratio=float(inlier_ratio),
            homography_quality=quality,
            correspondences=correspondences,
            transform=homography,
            meta={"good_matches": len(good)},
        )

    def visualize_matches(
        self, query: Sample, target: Sample, result: ComparisonResult
    ) -> Visualization:
        if result.correspondences is None or len(result.correspondences) == 0:
            return Visualization.empty()
        query_points = np.asarray(result.correspondences)[:, :2]
        overlay = Overlay.points_layer(query_points, color=(64, 200, 64, 255))
        return Visualization(overlays=(overlay,), target="query")
