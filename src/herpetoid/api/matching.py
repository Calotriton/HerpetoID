"""Feature and match value objects exchanged between algorithms and Core.

An algorithm turns a :class:`Sample` into a :class:`FeatureSet`, compares two feature sets into a
:class:`ComparisonResult`, and ranks a query against many candidates into a :class:`RankedResult`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .enums import AlgorithmFamily


@dataclass(slots=True)
class FeatureSet:
    """Features extracted from a :class:`Sample`. Core serializes these to a compressed ``.npz``."""

    algorithm_id: str
    kind: AlgorithmFamily
    descriptors: np.ndarray  # (N, D) local descriptors, or (D,) global embedding
    keypoints: np.ndarray | None = None  # (N, >=2) keypoint geometry, for keypoint algorithms
    #: Opaque catalog reference set by Core when loading candidate features; echoed into
    #: :attr:`MatchCandidate.target_ref` so rankings can be traced back to catalog entries.
    ref: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def count(self) -> int:
        """Number of descriptors (1 for a single global embedding)."""
        return 1 if self.descriptors.ndim == 1 else int(self.descriptors.shape[0])


@dataclass(slots=True)
class ComparisonResult:
    """Outcome of comparing two feature sets.

    ``score`` is in the algorithm's own semantics; ``normalized_score`` is mapped by the algorithm/Core
    to ``[0, 1]`` (higher = more similar) so results are comparable across algorithms and fusible.
    Correspondence data is optional and powers match visualization + geometric verification.
    """

    score: float
    normalized_score: float
    inliers: int = 0
    inlier_ratio: float = 0.0
    homography_quality: float = 0.0
    correspondences: np.ndarray | None = None  # (M, 4): x1, y1, x2, y2 matched point pairs
    transform: np.ndarray | None = None  # 3x3 homography, if estimated
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    """A single ranked candidate produced by :meth:`IdentificationAlgorithm.rank`."""

    target_ref: str
    score: float
    normalized_score: float
    rank: int


@dataclass(slots=True)
class RankedResult:
    """An ordered list of candidates from one algorithm (best first)."""

    algorithm_id: str
    candidates: tuple[MatchCandidate, ...] = ()

    def top(self, k: int) -> tuple[MatchCandidate, ...]:
        """The best ``k`` candidates."""
        return self.candidates[:k]
