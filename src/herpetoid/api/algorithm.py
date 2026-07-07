"""The abstract base class every identification algorithm inherits from.

Algorithms are species-agnostic: they see only a standardized :class:`Sample` and never know which
species produced it.

* **Strictly abstract**: :meth:`descriptor`, :meth:`extract_features`, :meth:`compare`.
* **Defaulted**: :meth:`initialize`, :meth:`save_features` / :meth:`load_features` (compressed ``.npz``
  round-trip), :meth:`rank` (compare-all + sort), :meth:`visualize_matches`.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path

import numpy as np

from .context import AlgorithmContext
from .descriptors import AlgorithmDescriptor
from .enums import AlgorithmFamily
from .imaging import Sample
from .matching import ComparisonResult, FeatureSet, MatchCandidate, RankedResult
from .visualization import Visualization


class IdentificationAlgorithm(ABC):
    """Base class for a reusable, species-agnostic matching algorithm."""

    @classmethod
    @abstractmethod
    def descriptor(cls) -> AlgorithmDescriptor:
        """Lightweight identity + capabilities for the registry."""

    def initialize(self, ctx: AlgorithmContext) -> None:
        """Optional one-time setup (load model/weights, select device). Default: no-op."""

    @abstractmethod
    def extract_features(self, sample: Sample) -> FeatureSet:
        """Compute the feature representation of a preprocessed :class:`Sample`."""

    @abstractmethod
    def compare(self, query: FeatureSet, target: FeatureSet) -> ComparisonResult:
        """Compare two feature sets, returning a score (+ optional correspondences)."""

    # -- serialization (algorithm owns the format; Core owns the path) --------------------------
    def save_features(self, features: FeatureSet, path: Path) -> None:
        """Persist a feature set as a compressed ``.npz`` (no pickle). Default implementation."""
        arrays: dict[str, np.ndarray] = {"descriptors": np.asarray(features.descriptors)}
        if features.keypoints is not None:
            arrays["keypoints"] = np.asarray(features.keypoints)
        meta = {
            "algorithm_id": features.algorithm_id,
            "kind": str(features.kind),
            "ref": features.ref,
            "meta": features.meta,
            "has_keypoints": features.keypoints is not None,
        }
        arrays["__meta__"] = np.frombuffer(json.dumps(meta).encode("utf-8"), dtype=np.uint8)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as handle:
            np.savez_compressed(handle, **arrays)  # type: ignore[arg-type]  # numpy stub lacks **kwds

    def load_features(self, path: Path) -> FeatureSet:
        """Inverse of :meth:`save_features`."""
        with np.load(path, allow_pickle=False) as data:
            meta = json.loads(bytes(data["__meta__"]).decode("utf-8"))
            descriptors = data["descriptors"]
            keypoints = data["keypoints"] if meta.get("has_keypoints") else None
        return FeatureSet(
            algorithm_id=meta["algorithm_id"],
            kind=AlgorithmFamily(meta["kind"]),
            descriptors=descriptors,
            keypoints=keypoints,
            ref=meta.get("ref"),
            meta=meta.get("meta", {}),
        )

    # -- ranking --------------------------------------------------------------------------------
    def rank(self, query: FeatureSet, candidates: Iterable[FeatureSet]) -> RankedResult:
        """Compare ``query`` against each candidate and sort by normalized score (best first)."""
        scored: list[tuple[str, float, float]] = []
        for candidate in candidates:
            result = self.compare(query, candidate)
            scored.append((candidate.ref or "", result.normalized_score, result.score))
        scored.sort(key=lambda item: item[1], reverse=True)
        ranked = tuple(
            MatchCandidate(target_ref=ref, score=raw, normalized_score=norm, rank=index + 1)
            for index, (ref, norm, raw) in enumerate(scored)
        )
        return RankedResult(algorithm_id=self.descriptor().algorithm_id, candidates=ranked)

    def visualize_matches(
        self, query: Sample, target: Sample, result: ComparisonResult
    ) -> Visualization:
        """Overlay data for a query/target comparison. Default: nothing (override to draw matches)."""
        return Visualization.empty()
