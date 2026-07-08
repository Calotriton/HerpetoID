"""Tests for domain entities, value objects and invariants."""

from __future__ import annotations

import pytest

from herpetoid import domain


def test_location_validation_and_properties() -> None:
    loc = domain.Location(latitude=42.5, longitude=1.0, name="Riu Aigua")
    assert loc.has_coordinates
    assert not loc.is_empty
    assert domain.Location().is_empty
    with pytest.raises(ValueError):
        domain.Location(latitude=100.0)
    with pytest.raises(ValueError):
        domain.Location(longitude=-200.0)


def test_plugin_ref_str() -> None:
    assert str(domain.PluginRef("orb", "1.0")) == "orb@1.0"
    assert str(domain.PluginRef("orb")) == "orb"


def test_observation_identification() -> None:
    obs = domain.Observation(species_id=1, observer="AL")
    assert not obs.is_identified
    obs.individual_id = 5
    assert obs.is_identified


def test_individual_defaults() -> None:
    ind = domain.Individual(species_id=1, code="CA-001")
    assert ind.sex is domain.Sex.UNDETERMINED
    assert ind.status is domain.IndividualStatus.ACTIVE
    assert ind.id is None


def test_match_decision() -> None:
    match = domain.Match(run_id=1, rank=1, score=10.0, normalized_score=0.9)
    assert not match.is_decided
    match.decision = domain.MatchDecision.CONFIRMED
    assert match.is_decided
