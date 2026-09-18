"""ORB identification algorithm: keypoint matching with geometric verification.

Pipeline: normalize the pattern's size -> ORB features -> BFMatcher (Hamming) -> Lowe ratio test ->
RANSAC similarity transform (rotation, uniform scale, translation) -> score from the number of
matches that agree on it. Species-agnostic: it consumes only a standardized
:class:`~herpetoid.api.Sample`.

**How the score is built, and why (v1.1).** Version 1.0 fitted a homography and averaged the inlier
count with the *inlier ratio*. The first real ground truth, verified by eye from iNaturalist
photographs of fire salamanders (82 recaptures, 78 different-animal pairs that looked alike to a
matcher), showed that both choices were wrong:

* the inlier ratio does not tell a recapture from a different animal (AUC 0.53), yet it was half the
  displayed score;
* a homography has eight degrees of freedom, enough for chance matches between different animals to
  agree on one. Its plausibility gate then zeroed 27% of the true recaptures, because their fits came
  out mirrored.

Two photographs of the same back differ by where the animal is, how it is turned and how large it
appears: a similarity transform, which chance matches rarely agree on and which cannot mirror. Its
inlier count alone ranks the verified pairs far better than the old score did (AUC 0.94 vs 0.79).
:func:`inlier_score` maps that count to ``[0, 1]`` so that the interface's bands mean something on
that data: *green* (>= 0.5) needs ten agreeing matches, *amber* (>= 0.25) six (v1.3; see below).

**v1.2: two guards against a collapse.** Searching a whole collection exposed a failure the first
verified pairs did not contain. Many query keypoints can match *the same* target keypoint, and a
similarity transform that shrinks the pattern to a point (scale ~0) then "agrees" with all of them.
Different animals reached up to 34 such inliers, in one comparison direction only, and 46% of the
different animals in the owner's second round of verified pairs were shown green. Matches are
therefore one-to-one (each target keypoint keeps its closest query match), and a transform whose
scale change exceeds ``max_scale_change`` scores zero. Measured on all 310 verified pairs (82+5
recaptures, 78+145 different animals): AUC 0.79 -> 0.94, different animals shown green 30% -> 0%,
recaptures shown green 67% -> 63%. The score also no longer depends on which photograph is the query.

**v1.3: green recalibrated for searching a whole collection.** The per-pair calibration (green at
eight inliers, no verified different animal reaching it) did not survive an exhaustive search. Among
~160k comparisons, the chance tail of different animals at 8-9 inliers produced dozens of greens, and
only 11 of 49 green pairs the owner checked were real recaptures. The false ones sat at the threshold
(median 8 inliers), the real ones higher (median 10). On the owner's 467 verified pairs (104
recaptures, 363 different animals):

=================  ==========================  ==================  ====================
green needs         precision in open search    recaptures green    different animals
=================  ==========================  ==================  ====================
8 inliers (v1.2)    22%                         63%                 10.5%
**10 (v1.3)**       **67%**                     **46%**             **0.8%**
12                  3/3                         33%                 0%
=================  ==========================  ==================  ====================

Green is therefore a strong *candidate*, not a verdict. A score that accounts for how many
candidates were searched would address the cause; this only moves the bar.

**v1.4: the pattern is resized before detection.** Two captures of one animal taken from different
distances produced descriptors that never corresponded. ORB's pyramid spans only ~3.6x, and a fixed
keypoint budget spread over a 2 048 px crop samples the pattern far more sparsely than the same
budget over 400 px. ``normalize_long_side`` (default 400, 0 disables) resizes the pattern first.
Isolated on the owner's 663 verified pairs -- same crops, same band-pass, only the resize changed:

===================  ==============  ==============  ===============  ===============
metric                ORB native      ORB 400 px      SIFT native      SIFT 400 px
===================  ==============  ==============  ===============  ===============
AUC                   0.784           **0.906**       **0.968**        0.949
recaptures found      31/144 green    **46/144**      **104/144**      89/144
===================  ==============  ==============  ===============  ===============

On round 5 -- the only population both recipes mined, so the least biased -- ORB goes from AUC 0.730
and 9 of 33 recaptures green to **0.905 and 19 of 33**, with AUC rising monotonically as the target
shrinks. It is an **ORB** fix: SIFT assigns every keypoint its own scale, was never scale-sensitive,
and measures *worse* normalized (in round 5 too, against its own selection bias). That is why this
lives in the algorithm and not in the species module, whose one ``Sample`` feeds both.

Keypoints stay in the resized frame, so the RANSAC tolerance is computed on it exactly as measured;
the factor rides in ``FeatureSet.meta`` (it survives the ``.npz`` round-trip) and :meth:`compare`
maps correspondences back into each ``Sample``'s own pixels, since ``visualize_matches`` never sees
the feature sets. Two caveats: it was measured on *automatic* crops rather than the hand-drawn
regions the application feeds in, and the closed-set benchmark cannot verify the transfer (it cannot
resolve anything below ~0.17 AUC -- ``docs/evaluation.md`` limitation 9). The application's crop also
carries a **fixed** 64 px margin, so a 2 000 px crop resized to 400 leaves ~13 px, under ORB's 31 px
edge threshold; the miner's padding was proportional. Re-measure when an external benchmark exists.

The constants are measured, not universal: they were fitted with the default ``nfeatures`` on the
fire-salamander pattern images. Different species or settings shift the count a chance match
reaches, so re-measure before trusting the bands elsewhere. Rankings within one query do not depend
on them.
"""

from __future__ import annotations

import math
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
    # RANSAC tolerance as a fraction of the matched region's extent (the spread of its keypoints), so
    # a match means the same on a small crop and a full-resolution one.
    "ransac_reproj_fraction": 0.018,
    "min_good_matches": 4,
    # A fitted transform that shrinks or enlarges the pattern by more than this is not a match: ORB's
    # own pyramid (scale 1.2, 8 levels) spans ~3.6x, so no genuine correspondence lies beyond it.
    "max_scale_change": 4.0,
    # Score calibration (module docstring): how many agreeing matches chance alone produces, and how
    # many more it takes to carry the score most of the way to 1.
    "chance_inliers": 3.0,
    "inlier_scale": 10.0,
    # Resize the pattern so its longer side is this many pixels before detecting (0 disables).
    # Distinct from ``ransac_reproj_fraction`` above: that makes the *tolerance* relative to the
    # region, this makes the *descriptors* comparable. ORB's pyramid spans only ~3.6x and a fixed
    # keypoint budget samples a 2048 px crop far more sparsely than a 400 px one, so two captures
    # taken at different distances produce descriptors that never correspond. On the 663
    # owner-verified pairs this lifted ORB from AUC 0.784 to 0.906 and recaptures-in-green from
    # 31/144 to 46/144; on round 5 -- the only population both recipes mined, so the least biased --
    # from 0.730 and 9/33 to 0.905 and 19/33. It belongs here rather than in the species module
    # because one Sample feeds both algorithms and SIFT, which sets each keypoint's own scale, is
    # measurably *worse* normalized (docs/evaluation.md 6.8).
    "normalize_long_side": 400,
}

_CONFIG_SCHEMA: dict[str, Any] = {
    "nfeatures": {"type": "int", "label": "ORB features", "min": 100, "max": 10000},
    "lowe_ratio": {"type": "float", "label": "Lowe ratio", "min": 0.5, "max": 0.95},
    "ransac_reproj_fraction": {
        "type": "float",
        "label": "RANSAC tolerance (fraction of region)",
        "min": 0.002,
        "max": 0.05,
    },
    "min_good_matches": {"type": "int", "label": "Min good matches", "min": 4, "max": 100},
    "max_scale_change": {"type": "float", "label": "Max scale change", "min": 1.5, "max": 10.0},
    "chance_inliers": {"type": "float", "label": "Chance inliers", "min": 0.0, "max": 50.0},
    "inlier_scale": {"type": "float", "label": "Inlier scale", "min": 0.5, "max": 100.0},
    "normalize_long_side": {
        "type": "int",
        "label": "Normalize pattern to (px, 0 = off)",
        "min": 0,
        "max": 4000,
    },
}


def inlier_score(inliers: int, chance_inliers: float, inlier_scale: float) -> float:
    """Map a count of geometrically agreeing matches to a ``[0, 1]`` similarity.

    Counts at or below what chance produces score 0; each further match adds evidence with
    diminishing returns, so tens of inliers and hundreds both read as near-certain.
    """
    excess = float(inliers) - float(chance_inliers)
    if excess <= 0.0 or inlier_scale <= 0.0:
        return 0.0
    return float(1.0 - math.exp(-excess / float(inlier_scale)))


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


def _extent(*keypoint_sets: np.ndarray) -> float:
    """The larger side of the area the keypoints cover, over all given sets (pixels)."""
    spans = [float(np.ptp(k[:, :2], axis=0).max()) for k in keypoint_sets if len(k) >= 2]
    return max(spans) if spans else 0.0


def _normalized(
    gray: np.ndarray, mask: np.ndarray | None, long_side: int
) -> tuple[np.ndarray, np.ndarray | None, float]:
    """``gray`` and its mask resized so the longer side is ``long_side``, plus the factor applied.

    The factor is returned rather than discarded because the detector then works in a frame of its
    own: keypoints come back in resized pixels, and anything drawn over the caller's ``Sample`` --
    the match overlay -- has to be mapped back through it.
    """
    if long_side <= 0:
        return gray, mask, 1.0
    longest = max(gray.shape[:2])
    if longest <= 0:
        return gray, mask, 1.0
    factor = long_side / float(longest)
    if abs(factor - 1.0) < 0.01:  # already there; resampling would only cost detail
        return gray, mask, 1.0
    size = (max(8, round(gray.shape[1] * factor)), max(8, round(gray.shape[0] * factor)))
    interpolation = cv2.INTER_AREA if factor < 1.0 else cv2.INTER_CUBIC
    resized = np.ascontiguousarray(cv2.resize(gray, size, interpolation=interpolation))
    if mask is None:
        return resized, None, factor
    scaled_mask = cv2.resize(mask, size, interpolation=cv2.INTER_NEAREST)
    return resized, np.ascontiguousarray(scaled_mask), factor


def _one_to_one(matches: list[Any]) -> list[Any]:
    """Keep, for every target keypoint, only its closest query match.

    Without this, dozens of query keypoints can pile onto one target keypoint, and RANSAC counts
    them all as agreeing with a transform that shrinks the pattern to that point.
    """
    kept: dict[int, Any] = {}
    for match in matches:
        best = kept.get(match.trainIdx)
        if best is None or match.distance < best.distance:
            kept[match.trainIdx] = match
    return sorted(kept.values(), key=lambda match: match.queryIdx)


def _transform_quality(transform: np.ndarray | None) -> float:
    """A [0, 1] plausibility of the fitted transform's scale change (1.0 = same size)."""
    if transform is None:
        return 0.0
    determinant = float(np.linalg.det(transform[:2, :2]))
    if not np.isfinite(determinant) or determinant <= 1e-8:
        return 0.0
    return float(max(0.0, 1.0 - abs(np.log(abs(determinant))) / 4.0))


class OrbAlgorithm(IdentificationAlgorithm):
    """ORB + BFMatcher(Hamming) + Lowe ratio + RANSAC similarity, on a size-normalized pattern."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config: dict[str, Any] = {**_DEFAULT_CONFIG, **(config or {})}
        self._orb: Any = None

    @classmethod
    def descriptor(cls) -> AlgorithmDescriptor:
        return AlgorithmDescriptor(
            algorithm_id="orb",
            name="ORB (keypoint matching)",
            version="1.4",
            family=AlgorithmFamily.KEYPOINT,
            score_semantics=ScoreSemantics.SIMILARITY,
            requires_grayscale=False,
            needs_gpu=False,
            description=(
                "ORB features with BFMatcher (Hamming), Lowe ratio test and a RANSAC similarity "
                "transform; scored by the number of matches that agree on it."
            ),
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
        gray, mask, resize = _normalized(gray, mask, int(self._config["normalize_long_side"]))
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
            # Keypoints are in the resized frame, so record what it took to get there. Serialized
            # with the features, so a candidate loaded from the catalog maps back the same way.
            meta={"resize": resize},
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
        good = _one_to_one(good)
        if len(good) < int(self._config["min_good_matches"]):
            return ComparisonResult(
                score=float(len(good)), normalized_score=0.0, meta={"good_matches": len(good)}
            )

        query_pts = np.array([query_kp[m.queryIdx][:2] for m in good], dtype=np.float32)
        target_pts = np.array([target_kp[m.trainIdx][:2] for m in good], dtype=np.float32)
        tolerance = max(
            1.0, float(self._config["ransac_reproj_fraction"]) * _extent(query_kp, target_kp)
        )
        affine, inlier_mask = cv2.estimateAffinePartial2D(
            query_pts,
            target_pts,
            method=cv2.RANSAC,
            ransacReprojThreshold=tolerance,
            maxIters=2000,
            confidence=0.995,
        )
        transform = None if affine is None else np.vstack([affine, [0.0, 0.0, 1.0]])
        scale = float(np.hypot(affine[0, 0], affine[1, 0])) if affine is not None else 0.0
        limit = float(self._config["max_scale_change"])
        # Shrinking the pattern to a point "agrees" with anything, so an implausible scale is no match.
        plausible = affine is not None and inlier_mask is not None and 1.0 / limit <= scale <= limit
        accepted = np.asarray(inlier_mask) if plausible else None
        inliers = int(accepted.sum()) if accepted is not None else 0
        inlier_ratio = inliers / len(good) if good else 0.0
        normalized = inlier_score(
            inliers, float(self._config["chance_inliers"]), float(self._config["inlier_scale"])
        )

        correspondences = None
        if accepted is not None and inliers > 0:
            flags = accepted.ravel().astype(bool)
            # Back into each Sample's own pixels. The detector worked on resized copies, but the
            # match overlay draws these points over the patterns the species module produced, and
            # the two images are resized by different amounts.
            query_resize = float(query.meta.get("resize", 1.0)) or 1.0
            target_resize = float(target.meta.get("resize", 1.0)) or 1.0
            correspondences = np.hstack(
                [query_pts[flags] / query_resize, target_pts[flags] / target_resize]
            )

        return ComparisonResult(
            score=float(inliers),
            normalized_score=normalized,
            inliers=inliers,
            inlier_ratio=float(inlier_ratio),
            homography_quality=_transform_quality(transform),
            correspondences=correspondences,
            transform=transform,
            meta={"good_matches": len(good), "tolerance_px": tolerance, "scale": scale},
        )

    def visualize_matches(
        self, query: Sample, target: Sample, result: ComparisonResult
    ) -> Visualization:
        if result.correspondences is None or len(result.correspondences) == 0:
            return Visualization.empty()
        query_points = np.asarray(result.correspondences)[:, :2]
        overlay = Overlay.points_layer(query_points, color=(64, 200, 64, 255))
        return Visualization(overlays=(overlay,), target="query")
