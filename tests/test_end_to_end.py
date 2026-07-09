"""End-to-end proof: drive the real GUI screens through the whole photo-ID workflow.

This is Claude's standing self-check. Unlike the focused unit/screen tests, it exercises the entire
pipeline *through the actual screens and services* — import -> mark ROI + code -> identify -> confirm ->
browse the catalog -> statistics — so a regression in the wiring *between* layers fails loudly here.

Keep this test (and add to it) whenever a feature touches the cross-screen workflow.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image as PilImage

from herpetoid.api import ROI
from herpetoid.application.project_service import ProjectService
from herpetoid.application.registry import PluginRegistry
from herpetoid.application.settings import SettingsService
from herpetoid.gui.main_window import MainWindow
from herpetoid.gui.screens.candidate_ranking import CandidateRankingScreen
from herpetoid.gui.screens.import_images import ImageImportScreen
from herpetoid.gui.screens.individuals import IndividualBrowserScreen
from herpetoid.gui.screens.observations import ObservationsScreen
from herpetoid.gui.screens.statistics import StatisticsScreen
from herpetoid.gui.state import AppState
from herpetoid.infrastructure.plugin_discovery import discover_entry_points
from herpetoid.infrastructure.settings_store import JsonSettingsStore

pytestmark = [pytest.mark.gui, pytest.mark.integration]


def _spots(seed: int, size: int = 256, count: int = 45) -> np.ndarray:
    rng = np.random.default_rng(seed)
    image = np.full((size, size), 255, np.uint8)
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


def _screen(window: MainWindow, cls: type) -> object:
    for index in range(window._stack.count()):
        widget = window._stack.widget(index)
        if isinstance(widget, cls):
            return widget
    raise AssertionError(f"no {cls.__name__} in the window")


def test_full_photo_id_workflow(tmp_path: Path, qtbot) -> None:
    cv2.setRNGSeed(11)
    registry = PluginRegistry()
    discover_entry_points(registry)
    # Isolated settings store: never touch the real user's settings.json / recent projects.
    settings = SettingsService(JsonSettingsStore(tmp_path / "settings.json"))
    state = AppState(
        registry=registry, project_service=ProjectService(app_version="e2e"), settings=settings
    )
    window = MainWindow(state)
    qtbot.addWidget(window)

    # 1) The whole app boots and every screen is reachable.
    for name in window.screen_names():
        window.navigate_to(name)
        assert window.current_screen_name() == name

    # 2) Create a project.
    state.create_project(tmp_path / "proj", "E2E study")
    assert state.project is not None
    catalog = state.catalog
    assert catalog is not None

    # 3) Import three captures through the Import screen: a base pattern, the SAME pattern rotated,
    #    and a DIFFERENT individual.
    base = _spots(1)
    files = {
        "base.png": base,
        "rotated.png": _rotate(base, 12),  # same individual, different pose
        "other.png": _spots(999),  # a different individual
    }
    for filename, gray in files.items():
        _save(tmp_path / filename, gray)
    importer = _screen(window, ImageImportScreen)
    assert importer.species_combo.count() >= 1  # Calotriton asper from the registry
    assert importer.import_files([tmp_path / name for name in files]) == 3
    assert catalog.observation_count() == 3

    # 4) In the Observations screen, mark an ROI and assign an individual code to each capture.
    def observation_id_for(filename: str) -> int:
        for observation in catalog.list_observations():
            assert observation.id is not None
            images = catalog.images_for(observation.id)
            if images and images[0].original_filename == filename:
                return observation.id
        raise AssertionError(f"no observation for {filename}")

    codes = {"base.png": "CA-001", "rotated.png": "CA-002", "other.png": "CA-003"}
    # Capture ids up front: saving sets observed_at, which re-sorts the table, so a plain row loop
    # would skip/duplicate rows. Select each observation by id from the freshly-refreshed list.
    code_by_id = {observation_id_for(filename): code for filename, code in codes.items()}
    editor = _screen(window, ObservationsScreen)
    for observation_id, code in code_by_id.items():
        row = next(
            r for r in range(editor.table.rowCount()) if editor._observations[r].id == observation_id
        )
        editor.table.selectRow(row)
        assert editor._current is not None and editor._current.id == observation_id
        editor.code_edit.setText(code)
        editor.viewer.set_roi(ROI.rectangle(10, 10, 236, 236))
        editor.save()

    # Every capture is now a cataloged individual with a marked ROI.
    assert catalog.individual_count() == 3
    assert len(catalog.comparable_observations()) == 3

    # 5) Identify the base capture against the catalog: the rotated same-individual must rank first.
    base_id = observation_id_for("base.png")
    rotated_id = observation_id_for("rotated.png")
    candidates = _screen(window, CandidateRankingScreen)
    candidates.query_combo.setCurrentIndex(candidates.query_combo.findData(base_id))
    candidates.algorithm_combo.setCurrentIndex(candidates.algorithm_combo.findData("orb"))
    candidates.identify()
    assert candidates._candidates, "identification returned no candidates"
    assert candidates._candidates[0].observation.id == rotated_id
    assert candidates.query_info.rowCount() > 0  # species-driven info panel populated

    # 6) Confirm the match: the base capture is linked to the rotated capture's individual.
    candidates.table.selectRow(0)
    candidates.confirm_same()
    linked = catalog.get_observation(base_id)
    rotated = catalog.get_observation(rotated_id)
    assert linked is not None and rotated is not None
    assert linked.individual_id == rotated.individual_id

    # 7) The Individuals catalog and the Statistics dashboard reflect the work.
    individuals = _screen(window, IndividualBrowserScreen)
    individuals._refresh()
    assert individuals.table.rowCount() >= 1
    statistics = _screen(window, StatisticsScreen)
    assert "Observations: 3" in statistics.summary_label.text()
