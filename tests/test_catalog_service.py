"""Tests for the CatalogService (species, import, counts) over a real bundle."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PilImage

from herpetoid.application.catalog_service import CatalogService
from herpetoid.application.project_service import ProjectService
from herpetoid.domain import PluginRef

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
