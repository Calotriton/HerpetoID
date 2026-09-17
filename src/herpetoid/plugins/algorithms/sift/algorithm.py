"""SIFT keypoints scored by how *distinctive* each match is across the whole catalog (LNBNN).

Pipeline: RootSIFT features on the species module's pattern image -> every query descriptor is looked
up against the descriptors of **all** candidates at once -> local naive Bayes nearest neighbour
weighting -> RANSAC similarity transform -> score = the weight of the matches that agree.

**Why a second algorithm rather than a change to ORB.** ORB counts agreeing keypoints, which treats a
blotch edge every fire salamander has exactly like a blotch arrangement unique to one animal. LNBNN
weighs each match by how much closer it is than the same descriptor's *next* neighbour elsewhere in the
catalog: a descriptor that resembles many animals earns almost nothing, a descriptor that resembles one
photograph and nothing else earns a lot. That needs the catalog, which is why the work happens in
:meth:`rank` — the one place an algorithm sees the query and every candidate together.

**Measured on the owner's closed-set benchmark** (69 photographs sampled by survey night, grouped by a
herpetologist *before* seeing any software, regions drawn by hand; 12 true recaptures among 2 346
pairs), against ORB 1.3 on the identical photographs and regions:

===========================================  ==============  ==================
measure                                       ORB 1.3         SIFT + LNBNN
===========================================  ==============  ==================
right animal ranked first                     6/21 (29%)      **12/21 (57%)**
median rank of the true partner               8               **1**
recaptures found, at most 4 false pairs       1/12            **5/12**
different pairs shown green                   0/2334          0/2334
===========================================  ==============  ==================

Neither method finds 6 of the 12 recaptures, so this is an improvement, not a solution.

**Score calibration.** The raw LNBNN weight is mapped to ``[0, 1]`` by :func:`lnbnn_score` so the
interface's bands keep their meaning on that data: *green* (>= 0.5) at a raw weight of ~1.0, which 5 of
12 recaptures reach and only 4 of 2 334 different pairs do; *amber* (>= 0.25) at ~0.5 (86 of 2 334
different pairs). As with ORB, the constants are measured on fire salamanders and must be re-measured
for another species.

:meth:`compare` (the Compare A/B screen) has no catalog to be distinctive against, so it falls back to a
ratio test plus the same geometric check, scored by agreeing matches. **That fallback is not
calibrated** — treat its number as a rough indication and trust the ranking instead.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
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
    MatchCandidate,
    Overlay,
    RankedResult,
    Sample,
    ScoreSemantics,
    Visualization,
)

_DEFAULT_CONFIG: dict[str, Any] = {
    "nfeatures": 1000,
    # LNBNN: this many neighbours vote, the next one is the normaliser they are measured against.
    "lnbnn_neighbours": 12,
    # Only the best-voted candidates are worth a geometric check (the expensive step).
    "verify_top": 20,
    "min_inliers": 6,
    # RANSAC tolerance as a fraction of the region's keypoint spread, so it means the same on a small
    # crop and a full-resolution one (as in ORB 1.2+).
    "ransac_reproj_fraction": 0.018,
    # Score calibration (module docstring): the weight chance alone produces, and how much more it
    # takes to carry the score most of the way to 1.
    "chance_score": 0.15,
    "score_scale": 1.2,
    # Only used by the pairwise fallback in compare().
    "lowe_ratio": 0.75,
}

_CONFIG_SCHEMA: dict[str, Any] = {
    "nfeatures": {"type": "int", "label": "SIFT features", "min": 100, "max": 10000},
    "lnbnn_neighbours": {"type": "int", "label": "LNBNN neighbours", "min": 2, "max": 50},
    "verify_top": {"type": "int", "label": "Candidates verified", "min": 1, "max": 200},
    "min_inliers": {"type": "int", "label": "Min agreeing matches", "min": 3, "max": 100},
    "ransac_reproj_fraction": {
        "type": "float",
        "label": "RANSAC tolerance (fraction of region)",
        "min": 0.002,
        "max": 0.05,
    },
    "chance_score": {"type": "float", "label": "Chance weight", "min": 0.0, "max": 10.0},
    "score_scale": {"type": "float", "label": "Weight scale", "min": 0.1, "max": 20.0},
    "lowe_ratio": {"type": "float", "label": "Lowe ratio (A/B compare)", "min": 0.5, "max": 0.95},
}


def lnbnn_score(weight: float, chance_score: float, score_scale: float) -> float:
    """Map a distinctiveness weight to a ``[0, 1]`` similarity (see the module docstring)."""
    excess = float(weight) - float(chance_score)
    if excess <= 0.0 or score_scale <= 0.0:
        return 0.0
    return float(1.0 - math.exp(-excess / float(score_scale)))


def _root_sift(descriptors: np.ndarray) -> np.ndarray:
    """L1-normalise then square-root: Euclidean distance on these behaves like a better metric."""
    values = descriptors.astype(np.float32)
    values /= values.sum(axis=1, keepdims=True) + 1e-7
    return np.sqrt(values)


def _extent(*keypoint_sets: np.ndarray) -> float:
    spans = [float(np.ptp(k[:, :2], axis=0).max()) for k in keypoint_sets if len(k) >= 2]
    return max(spans) if spans else 0.0


def _one_to_one(pairs: list[tuple[int, int, float]]) -> list[tuple[int, int, float]]:
    """Keep the strongest match per target keypoint: many-to-one agreement is blur, not pattern."""
    best: dict[int, tuple[int, int, float]] = {}
    for query_index, target_index, weight in pairs:
        current = best.get(target_index)
        if current is None or weight > current[2]:
            best[target_index] = (query_index, target_index, weight)
    return sorted(best.values(), key=lambda item: item[0])


class SiftLnbnnAlgorithm(IdentificationAlgorithm):
    """RootSIFT features ranked by catalog-wide distinctiveness (LNBNN) + geometric verification."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config: dict[str, Any] = {**_DEFAULT_CONFIG, **(config or {})}
        self._sift: Any = None

    @classmethod
    def descriptor(cls) -> AlgorithmDescriptor:
        return AlgorithmDescriptor(
            algorithm_id="sift_lnbnn",
            name="SIFT + distinctiveness (LNBNN)",
            version="1.0",
            family=AlgorithmFamily.KEYPOINT,
            score_semantics=ScoreSemantics.SIMILARITY,
            requires_grayscale=False,
            needs_gpu=False,
            description=(
                "RootSIFT keypoints weighted by how distinctive each match is across the whole "
                "catalog, then verified with a RANSAC similarity transform."
            ),
            config_schema=_CONFIG_SCHEMA,
            default_config=dict(_DEFAULT_CONFIG),
        )

    def initialize(self, ctx: AlgorithmContext) -> None:
        self._config = {**self._config, **dict(ctx.config)}
        self._sift = None  # rebuilt lazily with the new nfeatures

    def _detector(self) -> Any:
        if self._sift is None:
            self._sift = cv2.SIFT_create(nfeatures=int(self._config["nfeatures"]))  # type: ignore[attr-defined]
        return self._sift

    # -- features -----------------------------------------------------------------------------
    def extract_features(self, sample: Sample) -> FeatureSet:
        image = np.asarray(sample.image)
        if image.ndim == 3:
            image = cv2.cvtColor(np.ascontiguousarray(image[:, :, :3]), cv2.COLOR_RGB2GRAY)
        if image.dtype != np.uint8:
            low, high = float(image.min()), float(image.max())
            image = (
                np.zeros(image.shape, np.uint8)
                if high <= low
                else ((image - low) / (high - low) * 255.0).astype(np.uint8)
            )
        mask = None
        if sample.roi_mask is not None:
            mask = (np.asarray(sample.roi_mask) > 0).astype(np.uint8) * 255
        keypoints, descriptors = self._detector().detectAndCompute(np.ascontiguousarray(image), mask)
        if descriptors is None or not keypoints:
            return FeatureSet(
                algorithm_id="sift_lnbnn",
                kind=AlgorithmFamily.KEYPOINT,
                descriptors=np.empty((0, 128), np.float32),
                keypoints=np.empty((0, 4), np.float32),
            )
        geometry = np.array(
            [[kp.pt[0], kp.pt[1], kp.size, kp.angle] for kp in keypoints], dtype=np.float32
        )
        return FeatureSet(
            algorithm_id="sift_lnbnn",
            kind=AlgorithmFamily.KEYPOINT,
            descriptors=_root_sift(descriptors),
            keypoints=geometry,
        )

    # -- geometry -----------------------------------------------------------------------------
    def _verify(
        self, query: FeatureSet, target: FeatureSet, pairs: list[tuple[int, int, float]]
    ) -> tuple[int, float, np.ndarray | None, np.ndarray | None]:
        """(inliers, summed weight of the inliers, correspondences, transform) for matched pairs."""
        pairs = _one_to_one(pairs)
        if len(pairs) < int(self._config["min_inliers"]):
            return 0, 0.0, None, None
        query_kp = np.asarray(query.keypoints)
        target_kp = np.asarray(target.keypoints)
        a = np.array([query_kp[i][:2] for i, _, _ in pairs], np.float32)
        b = np.array([target_kp[j][:2] for _, j, _ in pairs], np.float32)
        tolerance = max(
            1.0, float(self._config["ransac_reproj_fraction"]) * _extent(query_kp, target_kp)
        )
        affine, mask = cv2.estimateAffinePartial2D(
            a, b, method=cv2.RANSAC, ransacReprojThreshold=tolerance, maxIters=2000, confidence=0.995
        )
        if affine is None or mask is None:
            return 0, 0.0, None, None
        flags = mask.ravel().astype(bool)
        inliers = int(flags.sum())
        if inliers < int(self._config["min_inliers"]):
            return 0, 0.0, None, None
        weight = float(sum(w for (_, _, w), keep in zip(pairs, flags, strict=True) if keep))
        transform = np.vstack([affine, [0.0, 0.0, 1.0]])
        return inliers, weight, np.hstack([a[flags], b[flags]]), transform

    # -- pairwise (Compare A/B; no catalog, so not the calibrated score) -----------------------
    def compare(self, query: FeatureSet, target: FeatureSet) -> ComparisonResult:
        query_desc = np.asarray(query.descriptors)
        target_desc = np.asarray(target.descriptors)
        if query_desc.shape[0] < 2 or target_desc.shape[0] < 2:
            return ComparisonResult(score=0.0, normalized_score=0.0)
        matcher = cv2.BFMatcher(cv2.NORM_L2)
        ratio = float(self._config["lowe_ratio"])
        pairs = [
            (m[0].queryIdx, m[0].trainIdx, float(m[1].distance - m[0].distance))
            for m in matcher.knnMatch(query_desc, target_desc, k=2)
            if len(m) == 2 and m[0].distance < ratio * m[1].distance
        ]
        inliers, weight, correspondences, transform = self._verify(query, target, pairs)
        return ComparisonResult(
            score=float(inliers),
            # Uncalibrated on purpose: without a catalog there is no distinctiveness to measure.
            normalized_score=lnbnn_score(weight, 0.0, max(1e-6, 2.0 * float(self._config["score_scale"]))),
            inliers=inliers,
            inlier_ratio=float(inliers / len(pairs)) if pairs else 0.0,
            correspondences=correspondences,
            transform=transform,
            meta={"good_matches": len(pairs), "lnbnn_weight": weight, "calibrated": False},
        )

    # -- ranking (the calibrated path) ---------------------------------------------------------
    def rank(self, query: FeatureSet, candidates: Iterable[FeatureSet]) -> RankedResult:
        """Score every candidate by how distinctive its matches are within this catalog."""
        catalog = list(candidates)
        usable = [c for c in catalog if np.asarray(c.descriptors).shape[0] >= 2]
        query_desc = np.asarray(query.descriptors, np.float32)
        if not usable or query_desc.shape[0] < 2:
            return RankedResult(
                algorithm_id="sift_lnbnn",
                candidates=tuple(
                    MatchCandidate(target_ref=c.ref or "", score=0.0, normalized_score=0.0, rank=i + 1)
                    for i, c in enumerate(catalog)
                ),
            )

        owner = np.concatenate([np.full(len(np.asarray(c.descriptors)), i) for i, c in enumerate(usable)])
        local = np.concatenate([np.arange(len(np.asarray(c.descriptors))) for c in usable])
        data = np.ascontiguousarray(np.concatenate([np.asarray(c.descriptors) for c in usable]), np.float32)
        neighbours = min(int(self._config["lnbnn_neighbours"]), max(1, len(data) - 1))
        index = cv2.flann_Index(data, {"algorithm": 1, "trees": 4})  # type: ignore[attr-defined]
        idx, dist = index.knnSearch(query_desc, neighbours + 1, params={"checks": 64})
        dist = np.sqrt(np.maximum(np.asarray(dist, np.float32), 0.0))

        # LNBNN: each vote is worth how much closer it is than the normaliser (the next neighbour).
        images = owner[idx]
        weights = np.clip(dist[:, -1:] - dist[:, :-1], 0.0, None)
        rows = np.repeat(np.arange(idx.shape[0]), neighbours)
        flat_image, flat_weight, flat_db = images[:, :-1].ravel(), weights.ravel(), idx[:, :-1].ravel()
        order = np.argsort(-flat_weight)
        _, first = np.unique(rows[order] * len(usable) + flat_image[order], return_index=True)
        selected = order[first]
        selected = selected[flat_weight[selected] > 0]
        votes = np.bincount(flat_image[selected], weights=flat_weight[selected], minlength=len(usable))

        scored: dict[str, tuple[float, float]] = {}
        for position in np.argsort(-votes)[: int(self._config["verify_top"])]:
            if votes[position] <= 0:
                break
            chosen = selected[flat_image[selected] == position]
            pairs = [
                (int(rows[k]), int(local[flat_db[k]]), float(flat_weight[k])) for k in chosen
            ]
            inliers, weight, _, _ = self._verify(query, usable[position], pairs)
            if inliers:
                scored[usable[position].ref or ""] = (weight, float(inliers))

        ranked = sorted(
            (
                (
                    c.ref or "",
                    *scored.get(c.ref or "", (0.0, 0.0)),
                )
                for c in catalog
            ),
            key=lambda item: (-item[1], -item[2], item[0]),
        )
        return RankedResult(
            algorithm_id="sift_lnbnn",
            candidates=tuple(
                MatchCandidate(
                    target_ref=ref,
                    score=weight,
                    normalized_score=lnbnn_score(
                        weight, float(self._config["chance_score"]), float(self._config["score_scale"])
                    ),
                    rank=position + 1,
                )
                for position, (ref, weight, _inliers) in enumerate(ranked)
            ),
        )

    def visualize_matches(
        self, query: Sample, target: Sample, result: ComparisonResult
    ) -> Visualization:
        if result.correspondences is None or len(result.correspondences) == 0:
            return Visualization.empty()
        points = np.asarray(result.correspondences)[:, :2]
        return Visualization(overlays=(Overlay.points_layer(points, color=(64, 200, 64, 255)),), target="query")
