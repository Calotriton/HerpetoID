"""Integration tests for the database layer: schema, repositories, EAV metadata, cascades."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime

import pytest
from sqlalchemy import func, select

from herpetoid.domain import (
    Image,
    ImageAspect,
    Individual,
    Location,
    Observation,
    PluginRef,
    Project,
    Sex,
    Species,
)
from herpetoid.infrastructure.db import Database
from herpetoid.infrastructure.db.models import ImageModel, MetadataModel
from herpetoid.infrastructure.db.repositories import (
    ImageRepository,
    IndividualRepository,
    ObservationRepository,
    ProjectRepository,
    SpeciesRepository,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def db() -> Iterator[Database]:
    database = Database.in_memory()
    database.create_schema()
    yield database
    database.dispose()


def test_project_singleton_roundtrip(db: Database) -> None:
    with db.session() as session:
        ProjectRepository(session).add(
            Project(name="Pyrenees 2026", uuid="uuid-1", description="x")
        )
    with db.session() as session:
        project = ProjectRepository(session).get()
    assert project is not None
    assert project.id is not None
    assert project.name == "Pyrenees 2026"
    assert project.created_at is not None  # server default populated


def test_full_catalog_roundtrip(db: Database) -> None:
    with db.session() as session:
        species = SpeciesRepository(session).add(
            Species(
                scientific_name="Calotriton asper",
                common_name="Pyrenean brook newt",
                module=PluginRef("calotriton_asper", "1.0"),
            )
        )
        assert species.id is not None
        species_id = species.id
        individual = IndividualRepository(session).add(
            Individual(species_id=species_id, code="CA-001", sex=Sex.FEMALE)
        )
        individual_id = individual.id
        observation = ObservationRepository(session).add(
            Observation(
                species_id=species_id,
                individual_id=individual_id,
                observer="AL",
                observed_at=datetime(2026, 6, 1, 10, 30),
                location=Location(latitude=42.6, longitude=1.0, name="Riu Aigua"),
                measurements={"svl": 52.3, "weight": 4.1, "sex": "female", "mature": True},
            )
        )
        observation_id = observation.id
        ImageRepository(session).add(
            Image(
                observation_id=observation_id,
                rel_path="images/ca001.jpg",
                width=800,
                height=600,
                aspect=ImageAspect.VENTRAL,
            )
        )

    with db.session() as session:
        species = SpeciesRepository(session).get_by_name("Calotriton asper")
        assert species is not None
        assert species.module is not None
        assert species.module.plugin_id == "calotriton_asper"

        individuals = IndividualRepository(session).list_for_species(species_id)
        assert len(individuals) == 1
        assert individuals[0].sex is Sex.FEMALE

        observations = ObservationRepository(session).list_for_individual(individual_id)
        assert len(observations) == 1
        obs = observations[0]
        assert obs.observer == "AL"
        assert obs.is_identified
        assert obs.location.latitude == 42.6
        assert obs.location.name == "Riu Aigua"
        # typed EAV metadata round-trips with correct Python types
        assert obs.measurements["svl"] == 52.3
        assert obs.measurements["weight"] == 4.1
        assert obs.measurements["sex"] == "female"
        assert obs.measurements["mature"] is True

        images = ImageRepository(session).list_for_observation(observation_id)
        assert len(images) == 1
        assert images[0].aspect is ImageAspect.VENTRAL
        assert images[0].width == 800


def test_link_individual(db: Database) -> None:
    with db.session() as session:
        species = SpeciesRepository(session).add(Species(scientific_name="Testus testus"))
        observation = ObservationRepository(session).add(Observation(species_id=species.id))
        individual = IndividualRepository(session).add(
            Individual(species_id=species.id, code="T-1")
        )
        assert not observation.is_identified
        obs_id, ind_id = observation.id, individual.id
        ObservationRepository(session).link_to_individual(obs_id, ind_id)
    with db.session() as session:
        observation = ObservationRepository(session).get(obs_id)
    assert observation is not None
    assert observation.individual_id == ind_id


def test_cascade_delete_removes_children(db: Database) -> None:
    with db.session() as session:
        species = SpeciesRepository(session).add(Species(scientific_name="Testus testus"))
        observation = ObservationRepository(session).add(
            Observation(species_id=species.id, measurements={"svl": 10.0})
        )
        obs_id = observation.id
        ImageRepository(session).add(Image(observation_id=obs_id, rel_path="a.jpg"))

    with db.session() as session:
        ObservationRepository(session).delete(obs_id)

    with db.session() as session:
        image_count = session.scalar(select(func.count()).select_from(ImageModel))
        metadata_count = session.scalar(select(func.count()).select_from(MetadataModel))
    assert image_count == 0
    assert metadata_count == 0
