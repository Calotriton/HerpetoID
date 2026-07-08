"""Test the PDF report exporter over a real bundle."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image as PilImage

from herpetoid.application.catalog_service import CatalogService
from herpetoid.application.export import ExportData
from herpetoid.application.project_service import ProjectService
from herpetoid.domain import PluginRef
from herpetoid.infrastructure.pdf_export import PdfExporter

pytestmark = pytest.mark.integration


def test_pdf_export_produces_valid_pdf(tmp_path: Path) -> None:
    context = ProjectService().create(tmp_path / "proj", "Study")
    catalog = CatalogService(context)
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    image = tmp_path / "i.png"
    PilImage.fromarray(np.full((32, 32, 3), 100, np.uint8)).save(image)
    observation = catalog.import_observation(
        species.id, [image], observer="AL", measurements={"svl": 40.0}
    )
    individual = catalog.create_individual(species.id, code="CA-001")
    assert observation.id is not None
    catalog.link_observation(observation.id, individual.id)

    data = ExportData(
        project=context.project,
        species=catalog.list_species(),
        individuals=catalog.list_individuals(),
        observations=catalog.list_observations(),
        images=catalog.list_images(),
    )
    destination = tmp_path / "report.pdf"
    PdfExporter(bundle_root=context.path, title="Test Report").export(data, destination)

    assert destination.exists()
    content = destination.read_bytes()
    assert content[:4] == b"%PDF"
    assert len(content) > 1000
    context.close()
