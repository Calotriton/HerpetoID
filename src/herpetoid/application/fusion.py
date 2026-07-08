"""Rank fusion for combining several algorithms' rankings into one.

Reciprocal Rank Fusion (RRF) is robust and score-scale-independent; a weighted variant is provided for
when per-algorithm confidence is meaningful.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from herpetoid.api import MatchCandidate, RankedResult


def reciprocal_rank_fusion(
    rankings: Sequence[RankedResult], *, top_k: int, k: int = 60
) -> RankedResult:
    """Fuse rankings by summing ``1 / (k + rank)`` across algorithms for each candidate."""
    scores: dict[str, float] = {}
    for ranked in rankings:
        for candidate in ranked.candidates:
            scores[candidate.target_ref] = scores.get(candidate.target_ref, 0.0) + 1.0 / (
                k + candidate.rank
            )
    return _to_ranked(scores, top_k)


def weighted_score_fusion(
    rankings: Sequence[RankedResult], *, top_k: int, weights: Mapping[str, float] | None = None
) -> RankedResult:
    """Fuse rankings by a weighted sum of normalized scores (default weight 1.0 per algorithm)."""
    scores: dict[str, float] = {}
    for ranked in rankings:
        weight = 1.0 if weights is None else weights.get(ranked.algorithm_id, 1.0)
        for candidate in ranked.candidates:
            scores[candidate.target_ref] = (
                scores.get(candidate.target_ref, 0.0) + weight * candidate.normalized_score
            )
    return _to_ranked(scores, top_k)


def _to_ranked(scores: Mapping[str, float], top_k: int) -> RankedResult:
    # Sort by descending score, breaking ties deterministically by ref.
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_k]
    candidates = tuple(
        MatchCandidate(target_ref=ref, score=score, normalized_score=score, rank=index + 1)
        for index, (ref, score) in enumerate(ordered)
    )
    return RankedResult(algorithm_id="fused", candidates=candidates)
