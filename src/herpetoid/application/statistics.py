"""Generic, field-driven statistics engine.

Universal statistics (counts, recaptures, date range) are always computed. Everything else is driven by
the species' declared :class:`~herpetoid.api.DerivedStatistic` specs, so a new species gets its own
means, ratios and growth curves with no changes here.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from herpetoid.api import Aggregation, DerivedStatistic, StatisticKind
from herpetoid.domain import Individual, Observation


def _to_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime(value.year, value.month, value.day)


def _aggregate(values: Sequence[float], aggregation: Aggregation) -> float:
    match aggregation:
        case Aggregation.MEAN:
            return statistics.fmean(values)
        case Aggregation.MEDIAN:
            return statistics.median(values)
        case Aggregation.MIN:
            return float(min(values))
        case Aggregation.MAX:
            return float(max(values))
        case Aggregation.SUM:
            return float(sum(values))
        case Aggregation.STD:
            return statistics.pstdev(values) if len(values) > 1 else 0.0
        case Aggregation.COUNT:
            return float(len(values))


@dataclass(frozen=True, slots=True)
class GrowthPoint:
    """A single point in an individual's growth series."""

    individual_id: int
    observed_at: datetime
    value: float


@dataclass(slots=True)
class StatisticsReport:
    """Computed project statistics."""

    individual_count: int = 0
    observation_count: int = 0
    recapture_count: int = 0
    recaptured_individual_count: int = 0
    first_observation: datetime | None = None
    last_observation: datetime | None = None
    aggregates: dict[str, float] = field(default_factory=dict)
    distributions: dict[str, dict[str, int]] = field(default_factory=dict)
    growth: dict[str, list[GrowthPoint]] = field(default_factory=dict)


class StatisticsService:
    """Computes universal + field-driven statistics for a catalog."""

    def compute(
        self,
        *,
        individuals: Sequence[Individual],
        observations: Sequence[Observation],
        derived: Sequence[DerivedStatistic] = (),
    ) -> StatisticsReport:
        report = StatisticsReport(
            individual_count=len(individuals), observation_count=len(observations)
        )
        self._compute_universal(report, observations)
        for spec in derived:
            self._apply_spec(report, spec, observations)
        return report

    @staticmethod
    def _compute_universal(report: StatisticsReport, observations: Sequence[Observation]) -> None:
        counts_by_individual: dict[int, int] = defaultdict(int)
        dates: list[datetime] = []
        for obs in observations:
            if obs.observed_at is not None:
                dates.append(_to_datetime(obs.observed_at))
            if obs.individual_id is not None:
                counts_by_individual[obs.individual_id] += 1
        report.recapture_count = sum(max(0, n - 1) for n in counts_by_individual.values())
        report.recaptured_individual_count = sum(1 for n in counts_by_individual.values() if n >= 2)
        if dates:
            report.first_observation = min(dates)
            report.last_observation = max(dates)

    def _apply_spec(
        self, report: StatisticsReport, spec: DerivedStatistic, observations: Sequence[Observation]
    ) -> None:
        if spec.kind is StatisticKind.DERIVED and spec.compute is not None:
            computed = [
                float(result)
                for obs in observations
                if (result := spec.compute(obs.measurements)) is not None
            ]
            if computed:
                report.aggregates[spec.key] = _aggregate(computed, spec.aggregation)
            return

        field_key = spec.source_field
        if field_key is None:
            return
        match spec.kind:
            case StatisticKind.AGGREGATE:
                values = [
                    float(value)
                    for obs in observations
                    if isinstance(value := obs.measurements.get(field_key), (int, float))
                    and not isinstance(value, bool)
                ]
                if values:
                    report.aggregates[spec.key] = _aggregate(values, spec.aggregation)
            case StatisticKind.DISTRIBUTION:
                report.distributions[spec.key] = self._distribution(observations, field_key)
            case StatisticKind.GROWTH:
                report.growth[spec.key] = self._growth(observations, field_key)
            case _:
                pass

    @staticmethod
    def _distribution(observations: Sequence[Observation], field_key: str) -> dict[str, int]:
        """Category counts over each individual's most recent value (unlinked observations counted individually)."""
        latest: dict[int, tuple[datetime, Any]] = {}
        counts: dict[str, int] = defaultdict(int)
        for obs in observations:
            value = obs.measurements.get(field_key)
            if value is None:
                continue
            if obs.individual_id is None:
                counts[str(value)] += 1
                continue
            when = _to_datetime(obs.observed_at) if obs.observed_at is not None else datetime.min
            previous = latest.get(obs.individual_id)
            if previous is None or when >= previous[0]:
                latest[obs.individual_id] = (when, value)
        for _, value in latest.values():
            counts[str(value)] += 1
        return dict(counts)

    @staticmethod
    def _growth(observations: Sequence[Observation], field_key: str) -> list[GrowthPoint]:
        """Per-individual time series (only individuals with at least two numeric points)."""
        by_individual: dict[int, list[GrowthPoint]] = defaultdict(list)
        for obs in observations:
            if obs.individual_id is None or obs.observed_at is None:
                continue
            value = obs.measurements.get(field_key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                by_individual[obs.individual_id].append(
                    GrowthPoint(obs.individual_id, _to_datetime(obs.observed_at), float(value))
                )
        series: list[GrowthPoint] = []
        for points in by_individual.values():
            if len(points) >= 2:
                series.extend(sorted(points, key=lambda point: point.observed_at))
        return series
