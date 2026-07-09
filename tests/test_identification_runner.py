"""End-to-end identification over a real bundle: same individual should rank above different ones."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image as PilImage

from herpetoid.api import ROI
from herpetoid.application.catalog_service import CatalogService
from herpetoid.application.identification import IdentificationService
from herpetoid.application.identification_runner import IdentificationRunner
from herpetoid.application.project_service import ProjectService
from herpetoid.application.registry import PluginRegistry
from herpetoid.domain import PluginRef
from herpetoid.infrastructure.plugin_discovery import discover_entry_points

pytestmark = pytest.mark.integration


def _spots(seed: int, size: int = 256, count: int = 45) -> np.ndarray:
    rng = np.random.default_rng(seed)
    image = np.full((size, size), 255, dtype=np.uint8)
    for _ in range(count):
        cx, cy = rng.integers(20, size - 20, size=2)
        ax, ay = rng.integers(5, 15, size=2)
        cv2.ellipse(
            image, (int(cx), int(cy)), (int(ax), int(ay)), int(rng.integers(0, 180)), 0, 360, 0, -1
        )
    return image


def _rotate(image: np.ndarray, degrees: float) -> np.ndarray:
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
    return cv2.warpAffine(image, matrix, (w, h), borderValue=255)


def _save(path: Path, gray: np.ndarray) -> None:
    PilImage.fromarray(np.stack([gray, gray, gray], axis=-1)).save(path)


def test_identification_runner_ranks_same_individual_first(tmp_path: Path) -> None:
    cv2.setRNGSeed(7)
    registry = PluginRegistry()
    discover_entry_points(registry)
    context = ProjectService().create(tmp_path / "proj", "P")
    catalog = CatalogService(context)
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None

    base = _spots(1)
    path_a, path_b, path_c = tmp_path / "a.png", tmp_path / "b.png", tmp_path / "c.png"
    _save(path_a, base)
    _save(path_b, _rotate(base, 10))  # the same individual, rotated
    _save(path_c, _spots(999))  # a different individual
    query = catalog.import_observation(species.id, [path_a], observer="A")
    same = catalog.import_observation(species.id, [path_b], observer="A")
    different = catalog.import_observation(species.id, [path_c], observer="A")
    assert query.id is not None

    # The catalog compares only against "previous captures": individuals with a marked ROI.
    for observation in (same, different):
        assert observation.id is not None
        individual = catalog.create_individual(species.id)
        catalog.link_observation(observation.id, individual.id)
        image = catalog.images_for(observation.id)[0]
        assert image.id is not None
        catalog.set_image_roi(image.id, ROI.rectangle(10, 10, 236, 236))

    runner = IdentificationRunner(context, registry, IdentificationService())
    candidates = runner.identify(query.id, "orb", top_k=2)
    assert candidates
    assert candidates[0].observation.id == same.id  # same individual (rotated) ranks first
    context.close()
