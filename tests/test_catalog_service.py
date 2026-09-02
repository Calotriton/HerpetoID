"""Tests for the CatalogService (species, import, counts) over a real bundle."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PilImage
from sqlalchemy import inspect

from herpetoid.application.catalog_service import CatalogService
from herpetoid.application.project_service import ProjectService
from herpetoid.domain import PluginRef
from herpetoid.infrastructure.db.database import Database

pytestmark = pytest.mark.integration


def _image(path: Path) -> None:
    PilImage.fromarray(np.zeros((16, 16, 3), np.uint8)).save(path)


def test_catalog_service_species_and_import(tmp_path: Path) -> None:
    context = ProjectService().create(tmp_path / "bundle", "B")
    catalog = CatalogService(context)

    first = catalog.ensure_species("Calotriton asper", module=PluginRef("calotriton_asper", "1.0"))
    again = catalog.ensure_species("Calotriton asper")  # idempotent
    assert first.id == again.id
    assert len(catalog.list_species()) == 1

    source = tmp_path / "newt.png"
    _image(source)
    assert first.id is not None
    observation = catalog.import_observation(
        first.id, [source], observer="AL", measurements={"svl": 42.0}
    )
    assert observation.id is not None
    assert catalog.observation_count() == 1
    stored = catalog.list_observations()
    assert stored[0].observer == "AL"
    assert stored[0].measurements["svl"] == 42.0
    assert list((tmp_path / "bundle" / "images").glob("*"))
    context.close()


def test_delete_observation_with_roi_and_individual(tmp_path: Path) -> None:
    """Deleting must cascade the ROI row too (the image_rois FK otherwise blocks it)."""
    from herpetoid.api import ROI

    context = ProjectService().create(tmp_path / "bundle", "B")
    catalog = CatalogService(context)
    species = catalog.ensure_species("Calotriton asper", module=PluginRef("calotriton_asper", "1.0"))
    assert species.id is not None
    source = tmp_path / "newt.png"
    _image(source)
    observation = catalog.import_observation(species.id, [source])
    assert observation.id is not None
    image = catalog.images_for(observation.id)[0]
    assert image.id is not None
    catalog.set_image_roi(image.id, ROI.rectangle(2, 2, 10, 10))
    individual = catalog.create_individual(species.id, code="CA-1")
    catalog.link_observation(observation.id, individual.id)

    catalog.delete_observation(observation.id)
    assert catalog.observation_count() == 0
    assert catalog.get_image_roi(image.id) is None
    assert catalog.individual_count() == 1  # the individual itself is kept


def test_observation_can_be_updated_repeatedly(tmp_path: Path) -> None:
    """Re-saving an observation with measurements must not trip the metadata UNIQUE index."""
    context = ProjectService().create(tmp_path / "bundle", "B")
    catalog = CatalogService(context)
    species = catalog.ensure_species("Calotriton asper", module=PluginRef("calotriton_asper", "1.0"))
    assert species.id is not None
    source = tmp_path / "newt.png"
    _image(source)
    observation = catalog.import_observation(species.id, [source], measurements={"svl": 40.0})
    assert observation.id is not None

    # Second save with the same field key previously raised sqlite3.IntegrityError.
    observation.observer = "AL"
    observation.measurements = {"svl": 41.0, "weight": 7.0}
    catalog.update_observation(observation)
    # Third save changing the values again.
    observation.measurements = {"svl": 42.5}
    catalog.update_observation(observation)

    reloaded = catalog.get_observation(observation.id)
    assert reloaded is not None
    assert reloaded.observer == "AL"
    assert reloaded.measurements == {"svl": 42.5}
    context.close()


def test_roi_persistence_and_observation_update(tmp_path: Path) -> None:
    from herpetoid.api import ROI, ROIKind

    context = ProjectService().create(tmp_path / "bundle", "B")
    catalog = CatalogService(context)
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    source = tmp_path / "newt.png"
    _image(source)
    observation = catalog.import_observation(species.id, [source])
    assert observation.id is not None
    image = catalog.images_for(observation.id)[0]
    assert image.id is not None

    # ROI round-trip
    assert catalog.get_image_roi(image.id) is None
    catalog.set_image_roi(image.id, ROI.rectangle(5, 6, 40, 30))
    loaded_roi = catalog.get_image_roi(image.id)
    assert loaded_roi is not None
    assert loaded_roi.kind is ROIKind.RECTANGLE
    assert loaded_roi.bounding_box() == (5, 6, 40, 30)

    # …and a ROI can be taken back off an image again, idempotently.
    assert catalog.clear_image_roi(image.id) is True
    assert catalog.get_image_roi(image.id) is None
    assert catalog.has_roi(observation.id) is False
    assert catalog.clear_image_roi(image.id) is False  # nothing left to remove
    catalog.set_image_roi(image.id, ROI.rectangle(5, 6, 40, 30))  # restored for the checks below
    assert catalog.get_image_roi(image.id) is not None

    # observation update (core fields + measurements)
    observation.observer = "BM"
    observation.notes = "a note"
    observation.measurements = {"svl": 55.0, "sex": "male"}
    catalog.update_observation(observation)
    reloaded = catalog.get_observation(observation.id)
    assert reloaded is not None
    assert reloaded.observer == "BM"
    assert reloaded.notes == "a note"
    assert reloaded.measurements["svl"] == 55.0
    assert reloaded.measurements["sex"] == "male"
    context.close()


def test_opening_an_older_bundle_adds_columns_its_tables_lack(tmp_path: Path) -> None:
    """A bundle outlives the version that wrote it: a new column must reach an existing project.

    ``create_all`` only adds missing *tables*, so before ``migrate_schema`` a researcher's existing
    project would keep working right up until the first query touching the new column.
    """
    from sqlalchemy import text

    from herpetoid.application.project_service import ProjectService

    context = ProjectService().create(tmp_path / "bundle", "B")
    catalog = CatalogService(context)
    species = catalog.ensure_species("Calotriton asper")
    assert species.id is not None
    source = tmp_path / "newt.png"
    _image(source)
    observation = catalog.import_observation(species.id, [source])
    assert observation.id is not None
    context.close()

    # Turn it back into a bundle written before the column existed.
    database = Database.at_path(tmp_path / "bundle" / "project.db")
    with database.engine.begin() as connection:
        connection.execute(text("ALTER TABLE images DROP COLUMN rotation"))
        assert "rotation" not in {c["name"] for c in inspect(database.engine).get_columns("images")}
    database.dispose()

    reopened = ProjectService().open(tmp_path / "bundle")
    columns = {c["name"] for c in inspect(reopened.database.engine).get_columns("images")}
    assert "rotation" in columns
    images = CatalogService(reopened).images_for(observation.id)
    assert images and images[0].rotation == 0  # existing rows get the declared default
    assert images[0].original_filename == "newt.png"  # ...and nothing else was disturbed
    reopened.close()


def test_a_rotation_is_remembered_across_reopening(tmp_path: Path) -> None:
    from herpetoid.application.project_service import ProjectService

    context = ProjectService().create(tmp_path / "bundle", "B")
    catalog = CatalogService(context)
    species = catalog.ensure_species("Calotriton asper")
    assert species.id is not None
    source = tmp_path / "newt.png"
    _image(source)
    observation = catalog.import_observation(species.id, [source])
    assert observation.id is not None
    image = catalog.images_for(observation.id)[0]
    assert image.id is not None and image.rotation == 0

    catalog.set_image_rotation(image.id, 270)
    context.close()

    reopened = ProjectService().open(tmp_path / "bundle")
    assert CatalogService(reopened).images_for(observation.id)[0].rotation == 270
    reopened.close()
