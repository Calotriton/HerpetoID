"""Catalog operations for an open project: species, importing observations, and counts.

Wraps the repositories + image store of a :class:`ProjectContext` behind task-oriented methods the GUI
calls (e.g. "import these image files as observations of this species").
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

from herpetoid.domain import Image, Individual, Observation, PluginRef, Species

from .project_service import ProjectContext


class CatalogService:
    def __init__(self, project: ProjectContext) -> None:
        self._project = project

    # -- species --------------------------------------------------------------------------------
    def list_species(self) -> list[Species]:
        from herpetoid.infrastructure.db.repositories import SpeciesRepository

        with self._project.database.session() as session:
            return SpeciesRepository(session).list()

    def ensure_species(
        self, scientific_name: str, *, common_name: str = "", module: PluginRef | None = None
    ) -> Species:
        from herpetoid.infrastructure.db.repositories import SpeciesRepository

        with self._project.database.session() as session:
            repository = SpeciesRepository(session)
            existing = repository.get_by_name(scientific_name)
            if existing is not None:
                return existing
            return repository.add(
                Species(scientific_name=scientific_name, common_name=common_name, module=module)
            )

    # -- import ---------------------------------------------------------------------------------
    def import_observation(
        self,
        species_id: int,
        image_paths: Sequence[Path],
        *,
        observer: str = "",
        observed_at: date | datetime | None = None,
        measurements: dict[str, Any] | None = None,
    ) -> Observation:
        """Import image file(s) into the bundle and record a new observation of them."""
        from herpetoid.infrastructure.db.repositories import (
            ImageRepository,
            ObservationRepository,
        )

        imported = [self._project.image_store.import_image(path) for path in image_paths]
        with self._project.database.session() as session:
            observation = ObservationRepository(session).add(
                Observation(
                    species_id=species_id,
                    observer=observer,
                    observed_at=observed_at,
                    measurements=measurements or {},
                )
            )
            observation_id = observation.id
            if observation_id is None:
                raise RuntimeError("observation was not assigned an id")
            images = ImageRepository(session)
            for meta in imported:
                images.add(
                    Image(
                        observation_id=observation_id,
                        rel_path=meta.rel_path,
                        original_filename=meta.original_filename,
                        file_hash=meta.file_hash,
                        width=meta.width,
                        height=meta.height,
                        image_format=meta.image_format,
                        thumbnail_path=meta.thumbnail_path,
                    )
                )
            return observation

    # -- queries --------------------------------------------------------------------------------
    def observation_count(self) -> int:
        from herpetoid.infrastructure.db.repositories import ObservationRepository

        with self._project.database.session() as session:
            return ObservationRepository(session).count()

    def individual_count(self) -> int:
        from herpetoid.infrastructure.db.repositories import IndividualRepository

        with self._project.database.session() as session:
            return IndividualRepository(session).count()

    def list_observations(self) -> list[Observation]:
        from herpetoid.infrastructure.db.repositories import ObservationRepository

        with self._project.database.session() as session:
            return ObservationRepository(session).list_all()

    def list_individuals(self) -> list[Individual]:
        from herpetoid.infrastructure.db.repositories import IndividualRepository

        with self._project.database.session() as session:
            return IndividualRepository(session).list_all()

    def images_for(self, observation_id: int) -> list[Image]:
        from herpetoid.infrastructure.db.repositories import ImageRepository

        with self._project.database.session() as session:
            return ImageRepository(session).list_for_observation(observation_id)
