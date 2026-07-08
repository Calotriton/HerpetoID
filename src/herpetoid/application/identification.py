"""The identification pipeline, orchestrated by Core.

Given a preprocessed query :class:`~herpetoid.api.Sample` and the catalog's stored features (per
algorithm), the service ranks candidates with each algorithm and fuses the rankings. The final call on
any candidate is always the user's -- this service only *proposes* ranked candidates.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from herpetoid.api import FeatureSet, IdentificationAlgorithm, RankedResult, Sample

from .fusion import reciprocal_rank_fusion


@dataclass(slots=True)
class IdentificationOutcome:
    """The result of an identification run: each algorithm's ranking plus a fused ranking."""

    per_algorithm: dict[str, RankedResult]
    fused: RankedResult


class IdentificationService:
    """Runs the query against the catalog with one or more algorithms and fuses the results."""

    def identify(
        self,
        *,
        query_sample: Sample,
        algorithms: Sequence[IdentificationAlgorithm],
        catalog_features: Mapping[str, Sequence[FeatureSet]],
        top_k: int = 3,
    ) -> IdentificationOutcome:
        """Rank the catalog per algorithm, then fuse.

        ``catalog_features`` maps an algorithm id to the catalog feature sets for that algorithm (each
        carrying its ``ref`` back to a catalog entry). Query features are extracted here from
        ``query_sample`` for each algorithm.
        """
        if not algorithms:
            raise ValueError("identify() requires at least one algorithm")

        per_algorithm: dict[str, RankedResult] = {}
        for algorithm in algorithms:
            algorithm_id = algorithm.descriptor().algorithm_id
            query_features = algorithm.extract_features(query_sample)
            candidates = list(catalog_features.get(algorithm_id, ()))
            ranking = algorithm.rank(query_features, candidates)
            per_algorithm[algorithm_id] = RankedResult(algorithm_id, ranking.candidates[:top_k])

        rankings = list(per_algorithm.values())
        if len(rankings) == 1:
            fused = RankedResult("fused", rankings[0].candidates[:top_k])
        else:
            fused = reciprocal_rank_fusion(rankings, top_k=top_k)
        return IdentificationOutcome(per_algorithm=per_algorithm, fused=fused)
