"""Run an identification query against a project's catalog.

Preprocesses the query and every other observation of the same species (via the species module),
extracts features (via the chosen algorithm), and ranks them (via the IdentificationService). Returns
candidates mapped back to observations/images/individuals for the GUI to present. The user makes the
final call.

v1 uses a full-image ROI and computes catalog features on demand; a persistent descriptor cache is a
future optimization (the schema already supports it).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from herpetoid.api import ROI, FeatureSet, SpeciesModule
from herpetoid.domain import Image, Individual, Observation, Species

from .catalog_service import CatalogService
from .identification import IdentificationService
from .project_service import ProjectContext
from .registry import PluginRegistry


@dataclass(slots=True)
class Candidate:
    observation: Observation
    image: Image
    individual: Individual | None
    score: float
    normalized_score: float
    rank: int


class IdentificationRunner:
    def __init__(
        self,
        project: ProjectContext,
        registry: PluginRegistry,
        identification: IdentificationService,
    ) -> None:
        self._project = project
        self._registry = registry
        self._identification = identification
        self._catalog = CatalogService(project)

    def identify(
        self, query_observation_id: int, algorithm_id: str, *, top_k: int = 3
    ) -> list[Candidate]:
        query = self._catalog.get_observation(query_observation_id)
        if query is None or query.id is None:
            return []
        module = self._module_for(self._catalog.get_species(query.species_id))
        if module is None:
            return []
        query_image = self._first_image(query.id)
        if query_image is None:
            return []

        algorithm = self._registry.create_algorithm(algorithm_id)
        roi = ROI.full_image()
        query_sample = module.preprocess(self._load(query_image), roi)

        catalog_features: list[FeatureSet] = []
        image_by_ref: dict[str, Image] = {}
        observation_by_ref: dict[str, Observation] = {}
        for observation in self._catalog.observations_for_species(query.species_id):
            if observation.id is None or observation.id == query.id:
                continue
            image = self._first_image(observation.id)
            if image is None:
                continue
            features = algorithm.extract_features(module.preprocess(self._load(image), roi))
            ref = str(observation.id)
            features.ref = ref
            catalog_features.append(features)
            image_by_ref[ref] = image
            observation_by_ref[ref] = observation

        outcome = self._identification.identify(
            query_sample=query_sample,
            algorithms=[algorithm],
            catalog_features={algorithm_id: catalog_features},
            top_k=top_k,
        )

        individuals = {i.id: i for i in self._catalog.list_individuals()}
        candidates: list[Candidate] = []
        for match in outcome.fused.candidates:
            candidate_obs = observation_by_ref.get(match.target_ref)
            candidate_image = image_by_ref.get(match.target_ref)
            if candidate_obs is None or candidate_image is None:
                continue
            individual = (
                individuals.get(candidate_obs.individual_id)
                if candidate_obs.individual_id
                else None
            )
            candidates.append(
                Candidate(
                    observation=candidate_obs,
                    image=candidate_image,
                    individual=individual,
                    score=match.score,
                    normalized_score=match.normalized_score,
                    rank=match.rank,
                )
            )
        return candidates

    def _module_for(self, species: Species | None) -> SpeciesModule | None:
        if species is None or species.module is None:
            return None
        if self._registry.module(species.module.plugin_id) is None:
            return None
        return self._registry.create_module(species.module.plugin_id)

    def _first_image(self, observation_id: int) -> Image | None:
        images = self._catalog.images_for(observation_id)
        return images[0] if images else None

    def _load(self, image: Image) -> np.ndarray:
        return self._project.image_store.load(image.rel_path)
