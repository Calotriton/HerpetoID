"""Integration tests for project bundle lifecycle and the file image store."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PilImage

from herpetoid.application.project_service import ProjectService
from herpetoid.domain import Image, Observation, Species
from herpetoid.infrastructure.db.repositories import (
    ImageRepository,
    ObservationRepository,
    SpeciesRepository,
)

pytestmark = pytest.mark.integration


def _make_image_file(path: Path, seed: int = 0, size: int = 64) -> None:
    array = np.random.default_rng(seed).integers(0, 256, size=(size, size, 3), dtype=np.uint8)
    PilImage.fromarray(array).save(path)


def test_create_open_and_import(tmp_path: Path) -> None:
    bundle = tmp_path / "study.herpetoid"
    service = ProjectService(app_version="0.1.0")

    context = service.create(bundle, "My Study", description="a test project")
    assert (bundle / "project.db").exists()
    assert (bundle / "images").is_dir()
    assert (bundle / "README.txt").exists()
    assert "My Study" in (bundle / "README.txt").read_text(encoding="utf-8")
    assert context.project.name == "My Study"
    assert context.project.id is not None

    source = tmp_path / "newt.png"
    _make_image_file(source)
    imported = context.image_store.import_image(source)
    assert (bundle / imported.rel_path).exists()
    assert (bundle / imported.thumbnail_path).exists()
    assert imported.width == 64
    assert imported.height == 64

    with context.database.session() as session:
        species = SpeciesRepository(session).add(Species(scientific_name="Calotriton asper"))
        observation = ObservationRepository(session).add(
            Observation(species_id=species.id, observer="AL")
        )
        observation_id = observation.id
        ImageRepository(session).add(
            Image(
                observation_id=observation_id,
                rel_path=imported.rel_path,
                original_filename=imported.original_filename,
                file_hash=imported.file_hash,
                width=imported.width,
                height=imported.height,
                image_format=imported.image_format,
                thumbnail_path=imported.thumbnail_path,
            )
        )
    context.close()

    # Reopen the bundle and confirm everything persisted, incl. loading the image back.
    reopened = service.open(bundle)
    assert reopened.project.name == "My Study"
    with reopened.database.session() as session:
        images = ImageRepository(session).list_for_observation(observation_id)
    assert len(images) == 1
    loaded = reopened.image_store.load(imported.rel_path)
    assert loaded.ndim == 3
    assert loaded.shape[2] == 3
    reopened.close()


def test_open_missing_project_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        ProjectService().open(tmp_path / "does-not-exist")


def test_create_refuses_nonempty_directory(tmp_path: Path) -> None:
    existing = tmp_path / "occupied"
    existing.mkdir()
    (existing / "file.txt").write_text("hi")
    with pytest.raises(FileExistsError):
        ProjectService().create(existing, "X")
