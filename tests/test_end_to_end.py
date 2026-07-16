"""End-to-end proof: drive the real GUI screens through the whole photo-ID workflow.

This is Claude's standing self-check. Unlike the focused unit/screen tests, it exercises the entire
pipeline *through the actual shell* — import -> mark ROI + code -> identify -> confirm -> browse the
catalog -> statistics — so a regression in the wiring *between* layers fails loudly here.

Keep this test (and add to it) whenever a feature touches the cross-screen workflow.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image as PilImage

from herpetoid.api import ROI
from herpetoid.application.catalog_service import pending_code
from herpetoid.application.project_service import ProjectService
from herpetoid.application.registry import PluginRegistry
from herpetoid.application.settings import SettingsService
from herpetoid.gui.main_window import MainWindow
from herpetoid.gui.screens.identification import IdentificationScreen
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

    # 1) The whole app boots: every workflow tab is reachable and the legacy names still resolve.
    for name in window.screen_names():
        window.navigate_to(name)
        assert window.current_screen_name() == name
    window.navigate_to("Candidates")  # legacy Home-card destinations map onto the new shell
    assert window.current_screen_name() == "Identification"

    # 2) Create a project. The dock's project tree picks it up.
    state.create_project(tmp_path / "proj", "E2E study")
    assert state.project is not None
    catalog = state.catalog
    assert catalog is not None
    assert window._dock.tree.topLevelItem(0).text(0) == "E2E study"

    # 3) Import three captures through the Import dialog: a base pattern, the SAME pattern rotated,
    #    and a DIFFERENT individual.
    base = _spots(1)
    files = {
        "base.png": base,
        "rotated.png": _rotate(base, 12),  # same individual, different pose
        "other.png": _spots(999),  # a different individual
    }
    for filename, gray in files.items():
        _save(tmp_path / filename, gray)
    importer = window.open_dialog("Import")
    assert isinstance(importer, ImageImportScreen)
    assert importer.species_combo.count() >= 1  # Calotriton asper from the registry
    assert importer.import_files([tmp_path / name for name in files]) == 3
    assert catalog.observation_count() == 3
    dock_root = window._dock.tree.topLevelItem(0)
    dock_lines = [dock_root.child(i).text(0) for i in range(dock_root.childCount())]
    assert "Observations (3)" in dock_lines  # the dock tree tracks the import live

    # 4) In the Observations tab, mark an ROI and assign an individual code to each capture.
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
    editor = window.find_screen(ObservationsScreen)
    assert isinstance(editor, ObservationsScreen)
    for observation_id, code in code_by_id.items():
        editor.select_observation(observation_id)
        assert editor._current is not None and editor._current.id == observation_id
        assert editor.save_button.text() == "Save observation"  # never saved -> editable
        editor.code_edit.setText(code)
        editor.viewer.set_roi(ROI.rectangle(10, 10, 236, 236))
        editor.save()
        # Saving pops a toast: success + what is still missing (observer, notes, SVL, …).
        assert not editor.toast.isHidden()
        assert "Observation saved successfully" in editor.toast.text()
        assert "Missing information" in editor.toast.text()
        for missing in ("Observer", "Notes", "SVL"):
            assert missing in editor.toast.text()
        assert "Individual code" not in editor.toast.text()  # a code was typed
        assert "ROI" not in editor.toast.text()  # a ROI was marked

    # Saving does NOT create individuals — the typed codes are pending until the user confirms
    # them on the Identification tab. All three are queryable (they have a ROI).
    assert catalog.individual_count() == 0
    assert len(catalog.comparable_observations()) == 3

    # A saved observation re-opens LOCKED behind an "Edit" button; clicking it unlocks the form
    # ("Save changes"), and re-saving reports "Edits saved" while keeping the same observation.
    assert editor.save_button.text() == "Edit"
    assert not editor.observer_edit.isEnabled()
    editor.save_button.click()  # enter edit mode
    assert editor.save_button.text() == "Save changes"
    assert editor.observer_edit.isEnabled()
    editor.observer_edit.setText("AL")
    editor.save_button.click()  # save the edits
    assert "Edits saved successfully" in editor.toast.text()
    assert editor.save_button.text() == "Edit"  # locked again after saving
    edited = catalog.get_observation(observation_id_for("other.png"))
    assert edited is not None and edited.observer == "AL"
    assert pending_code(edited) == "CA-003"  # the edit kept the observation's pending code

    # 5) Enrol the two known captures: identify each (an empty catalog yields no candidates) and
    #    confirm them as NEW individuals — this is the step that actually creates CA-002 / CA-003.
    base_id = observation_id_for("base.png")
    rotated_id = observation_id_for("rotated.png")
    other_id = observation_id_for("other.png")
    identification = window.find_screen(IdentificationScreen)
    assert isinstance(identification, IdentificationScreen)
    identification.algorithm_combo.setCurrentIndex(
        identification.algorithm_combo.findData("orb")
    )
    identification.query_combo.setCurrentIndex(identification.query_combo.findData(rotated_id))
    identification.identify()
    assert not identification._candidates  # nothing enrolled yet to match against
    # An empty catalog would look like "nothing happened" — instead a dialog offers to enrol this
    # query as the FIRST individual of the project (or cancel to go back).
    first_dialog = identification._first_dialog
    assert first_dialog is not None and first_dialog.isVisible()
    assert identification._first_mark_button is not None
    identification._first_mark_button.click()
    # The non-default code CA-002 was already typed in the editor, so no code prompt is needed.
    assert identification._first_code_dialog is None
    assert catalog.individual_count() == 1
    assert "first individual" in identification.status_label.text()
    identification.query_combo.setCurrentIndex(identification.query_combo.findData(other_id))
    identification.identify()  # CA-002 is enrolled now, so a (weak) candidate may rank
    identification.mark_new()  # …but the scientist decides this is a different animal
    assert catalog.individual_count() == 2  # CA-002 and CA-003, from their pending codes
    assert {i.code for i in catalog.list_individuals()} == {"CA-002", "CA-003"}

    # 6) Identify the base capture against the catalog: the rotated same-individual must rank
    #    first, and selecting its card lazily computes + renders the pairwise match evidence.
    identification.query_combo.setCurrentIndex(identification.query_combo.findData(base_id))
    identification.identify()
    assert identification._candidates, "identification returned no candidates"
    assert identification._candidates[0].observation.id == rotated_id
    assert identification.query_panel.info.rowCount() > 0  # species-driven info panel populated
    assert base_id in catalog.identified_observation_ids()  # the run was recorded

    identification.select_candidate(0)
    assert identification.overlay.viewer.has_image()  # match composite rendered
    card = identification.cards.itemWidget(identification.cards.item(0))
    assert "inliers" in card.detail_label.text()  # match evidence back-filled on the card

    # Confirm the match: the base capture joins the rotated capture's individual; its own pending
    # code CA-001 is superseded (no phantom third individual). The base capture is open in the
    # Observations editor while we confirm — the editor must pick up the new assignment (same-row
    # refreshes fire no selection signal, which once left a stale, unassigned copy behind).
    editor.select_observation(base_id)
    identification.confirm_same()
    linked = catalog.get_observation(base_id)
    rotated = catalog.get_observation(rotated_id)
    assert linked is not None and rotated is not None
    assert linked.individual_id == rotated.individual_id
    assert catalog.individual_count() == 2
    dock_root = window._dock.tree.topLevelItem(0)
    dock_lines = [dock_root.child(i).text(0) for i in range(dock_root.childCount())]
    assert "Individuals (2)" in dock_lines
    assert "Recaptures: 1" in window._dock.stats_label.text()  # base is now a recapture of CA-002

    # 7) Renaming a confirmed observation's code renames its individual in place — it must NOT
    #    unassign the observation into a pending state that needs identification again. Deliberately
    #    no re-select here: the editor still shows the row selected before the confirm above.
    confirmed_individual_id = linked.individual_id
    assert confirmed_individual_id is not None
    assert editor._current is not None and editor._current.individual_id == confirmed_individual_id
    assert editor.save_button.text() == "Edit"  # saved earlier -> locked; unlock to rename
    editor.save_button.click()
    editor.code_edit.setText("CA-002-renamed")
    editor.save()
    renamed = catalog.get_observation(base_id)
    assert renamed is not None
    assert renamed.individual_id == confirmed_individual_id  # still the same individual
    assert pending_code(renamed) is None  # no pending re-identification
    assert catalog.individual_count() == 2  # renamed, not duplicated
    kept = catalog.get_individual(confirmed_individual_id)
    assert kept is not None and kept.code == "CA-002-renamed"

    # 8) The Individuals catalog and the Statistics dashboard reflect the work.
    individuals = window.find_screen(IndividualBrowserScreen)
    assert isinstance(individuals, IndividualBrowserScreen)
    individuals._refresh()
    assert individuals.table.rowCount() >= 1
    statistics = window.find_screen(StatisticsScreen)
    assert isinstance(statistics, StatisticsScreen)
    assert "Observations: 3" in statistics.summary_label.text()

    # 9) The shell itself: the View toggle collapses the project panel and restores it.
    window.show()
    toggle = window._dock.toggleViewAction()
    assert window._dock.isVisible()
    toggle.trigger()
    assert not window._dock.isVisible()
    toggle.trigger()
    assert window._dock.isVisible()
