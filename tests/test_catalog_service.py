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
