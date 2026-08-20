"""Catalog operations for an open project: species, importing observations, and counts.

Wraps the repositories + image store of a :class:`ProjectContext` behind task-oriented methods the GUI
calls (e.g. "import these image files as observations of this species").
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

from herpetoid.api import ROI
from herpetoid.domain import Image, Individual, Observation, PluginRef, Sex, Species

from .project_service import ProjectContext

#: Reserved observation-metadata key holding an individual code the user typed in the editor but has
#: not yet confirmed in the Identification tab. Keys starting with "_" are internal: they are hidden
#: from exports and never come from a species module (module field keys are plain identifiers).
PENDING_CODE_KEY = "_pending_code"

#: Reserved observation-metadata key set the first time the user explicitly saves the observation in
#: the editor. It drives the editor's Save/Edit cycle: saved observations open locked behind an
#: "Edit" button instead of a blank "Save observation" one.
SAVED_KEY = "_saved"


def pending_code(observation: Observation) -> str | None:
    """The observation's unconfirmed individual code, if any."""
    value = observation.measurements.get(PENDING_CODE_KEY)
    return str(value) if value else None


def is_saved(observation: Observation) -> bool:
    """True once the user has explicitly saved this observation in the editor."""
    return bool(observation.measurements.get(SAVED_KEY))


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

    def list_images(self) -> list[Image]:
        from herpetoid.infrastructure.db.repositories import ImageRepository

        with self._project.database.session() as session:
            return ImageRepository(session).list_all()

    # -- individuals & linking ------------------------------------------------------------------
    def get_observation(self, observation_id: int) -> Observation | None:
        from herpetoid.infrastructure.db.repositories import ObservationRepository

        with self._project.database.session() as session:
            return ObservationRepository(session).get(observation_id)

    def get_species(self, species_id: int) -> Species | None:
        from herpetoid.infrastructure.db.repositories import SpeciesRepository

        with self._project.database.session() as session:
            return SpeciesRepository(session).get(species_id)

    def observations_for_species(self, species_id: int) -> list[Observation]:
        from herpetoid.infrastructure.db.repositories import ObservationRepository

        with self._project.database.session() as session:
            return ObservationRepository(session).list_for_species(species_id)

    def observations_for_individual(self, individual_id: int) -> list[Observation]:
        from herpetoid.infrastructure.db.repositories import ObservationRepository

        with self._project.database.session() as session:
            return ObservationRepository(session).list_for_individual(individual_id)

    def create_individual(
        self, species_id: int, *, code: str = "", sex: Sex = Sex.UNDETERMINED, notes: str = ""
    ) -> Individual:
        from herpetoid.infrastructure.db.repositories import IndividualRepository

        with self._project.database.session() as session:
            repository = IndividualRepository(session)
            if not code:
                code = f"IND-{len(repository.list_for_species(species_id)) + 1:03d}"
            return repository.add(
                Individual(species_id=species_id, code=code, sex=sex, notes=notes)
            )

    def get_individual(self, individual_id: int) -> Individual | None:
        from herpetoid.infrastructure.db.repositories import IndividualRepository

        with self._project.database.session() as session:
            return IndividualRepository(session).get(individual_id)

    def update_individual(self, individual: Individual) -> None:
        from herpetoid.infrastructure.db.repositories import IndividualRepository

        with self._project.database.session() as session:
            IndividualRepository(session).update(individual)

    def find_individual_by_code(self, species_id: int, code: str) -> Individual | None:
        from herpetoid.infrastructure.db.repositories import IndividualRepository

        with self._project.database.session() as session:
            return IndividualRepository(session).get_by_code(species_id, code)

    def has_roi(self, observation_id: int) -> bool:
        """True if the observation's first image has a marked ROI."""
        images = self.images_for(observation_id)
        if not images or images[0].id is None:
            return False
        return self.get_image_roi(images[0].id) is not None

    def record_identification(self, observation_id: int, algorithm_id: str = "") -> None:
        """Record that this observation was run through identification (a query in Candidates)."""
        from herpetoid.infrastructure.db.repositories import MatchRunRepository

        images = self.images_for(observation_id)
        if not images or images[0].id is None:
            return
        with self._project.database.session() as session:
            MatchRunRepository(session).add(images[0].id, algorithm_id)

    def identified_observation_ids(self) -> set[int]:
        """Observations that have been run through identification at least once (see Candidates)."""
        from herpetoid.infrastructure.db.repositories import MatchRunRepository

        with self._project.database.session() as session:
            return MatchRunRepository(session).identified_observation_ids()

    def comparable_observations(self) -> list[Observation]:
        """Observations that can be *selected* for identification / comparison: those with a marked ROI.

        A pattern region is the minimum needed to match. The observation need not be assigned to an
        individual yet — that is exactly what the Candidates/Comparison screens help decide. (The
        catalog side of a ranking still only counts individuals with an ROI as "previous captures".)
        """
        return [
            observation
            for observation in self.list_observations()
            if observation.id is not None and self.has_roi(observation.id)
        ]

    def link_observation(self, observation_id: int, individual_id: int | None) -> None:
        from herpetoid.infrastructure.db.repositories import ObservationRepository

        with self._project.database.session() as session:
            ObservationRepository(session).link_to_individual(observation_id, individual_id)

    def update_observation(self, observation: Observation) -> None:
        from herpetoid.infrastructure.db.repositories import ObservationRepository

        with self._project.database.session() as session:
            ObservationRepository(session).update(observation)

    def delete_observation(self, observation_id: int) -> None:
        """Delete an observation and (via cascade) its image rows, metadata and ROI.

        Image *files* are content-addressed and may be shared by other observations, so they are left
        on disk rather than risk removing a file another observation still points to.
        """
        from herpetoid.infrastructure.db.repositories import ObservationRepository

        with self._project.database.session() as session:
            ObservationRepository(session).delete(observation_id)

    def get_image_roi(self, image_id: int) -> ROI | None:
        from herpetoid.infrastructure.db.repositories import ImageRepository

        with self._project.database.session() as session:
            return ImageRepository(session).get_roi(image_id)

    def set_image_roi(self, image_id: int, roi: ROI) -> None:
        from herpetoid.infrastructure.db.repositories import ImageRepository

        with self._project.database.session() as session:
            ImageRepository(session).set_roi(image_id, roi)

    def clear_image_roi(self, image_id: int) -> bool:
        """Forget an image's ROI. Returns whether one was stored. Idempotent."""
        from herpetoid.infrastructure.db.repositories import ImageRepository

        with self._project.database.session() as session:
            return ImageRepository(session).clear_roi(image_id)
