"""Tests for the generic, field-driven statistics engine."""

from __future__ import annotations

from datetime import datetime

import pytest

from herpetoid.api import Aggregation, DerivedStatistic, StatisticKind
from herpetoid.application.statistics import StatisticsService
from herpetoid.domain import Individual, Observation


def _catalog() -> tuple[list[Individual], list[Observation]]:
    individuals = [
        Individual(species_id=1, code="I1", id=1),
        Individual(species_id=1, code="I2", id=2),
    ]
    observations = [
        Observation(
            species_id=1,
            individual_id=1,
            observed_at=datetime(2026, 1, 1),
            measurements={"svl": 40.0, "sex": "female"},
        ),
        Observation(
            species_id=1,
            individual_id=1,
            observed_at=datetime(2026, 3, 1),
            measurements={"svl": 45.0, "sex": "female"},
        ),
        Observation(
            species_id=1,
            individual_id=1,
            observed_at=datetime(2026, 6, 1),
            measurements={"svl": 50.0, "sex": "female"},
        ),
        Observation(
            species_id=1,
            individual_id=2,
            observed_at=datetime(2026, 2, 1),
            measurements={"svl": 30.0, "sex": "male"},
        ),
        Observation(
            species_id=1,
            individual_id=None,
            observed_at=datetime(2026, 4, 1),
            measurements={"svl": 20.0, "sex": "undetermined"},
        ),
    ]
    return individuals, observations


def test_universal_statistics() -> None:
    individuals, observations = _catalog()
    report = StatisticsService().compute(individuals=individuals, observations=observations)
    assert report.individual_count == 2
    assert report.observation_count == 5
    assert report.recapture_count == 2  # I1 seen 3x -> 2 recaptures; I2 seen 1x -> 0
    assert report.recaptured_individual_count == 1
    assert report.first_observation == datetime(2026, 1, 1)
    assert report.last_observation == datetime(2026, 6, 1)


def test_field_driven_statistics() -> None:
    individuals, observations = _catalog()
    derived = [
        DerivedStatistic("mean_svl", "Mean SVL", StatisticKind.AGGREGATE, source_field="svl"),
        DerivedStatistic("sex_ratio", "Sex ratio", StatisticKind.DISTRIBUTION, source_field="sex"),
        DerivedStatistic("growth", "Growth", StatisticKind.GROWTH, source_field="svl"),
        DerivedStatistic(
            "max_svl",
            "Max SVL",
            StatisticKind.AGGREGATE,
            source_field="svl",
            aggregation=Aggregation.MAX,
        ),
        DerivedStatistic(
            "svl_derived",
            "SVL via callable",
            StatisticKind.DERIVED,
            compute=lambda values: values.get("svl"),
        ),
    ]
    report = StatisticsService().compute(
        individuals=individuals, observations=observations, derived=derived
    )
    assert report.aggregates["mean_svl"] == pytest.approx(185.0 / 5)
    assert report.aggregates["max_svl"] == 50.0
    assert report.aggregates["svl_derived"] == pytest.approx(185.0 / 5)
    # sex ratio uses each individual's most-recent value; unlinked obs counted on its own
    assert report.distributions["sex_ratio"] == {"female": 1, "male": 1, "undetermined": 1}
    # only individual 1 has >= 2 SVL points
    growth = report.growth["growth"]
    assert [point.value for point in growth if point.individual_id == 1] == [40.0, 45.0, 50.0]
    assert all(point.individual_id == 1 for point in growth)


def test_empty_catalog() -> None:
    report = StatisticsService().compute(individuals=[], observations=[])
    assert report.individual_count == 0
    assert report.observation_count == 0
    assert report.first_observation is None
