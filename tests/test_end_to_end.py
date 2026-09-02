"""End-to-end proof: drive the real GUI screens through the whole photo-ID workflow.

This is Claude's standing self-check. Unlike the focused unit/screen tests, it exercises the entire
pipeline *through the actual shell* — import -> mark ROI + code -> identify -> confirm -> browse the
catalog -> statistics — so a regression in the wiring *between* layers fails loudly here.

Two species are driven, because "Core hard-codes nothing about a species" is only true if a second,
differently-shaped module goes through the same screens: *Calotriton asper* (greyscale ventral
pattern, hand-drawn ROI) in :func:`test_full_photo_id_workflow`, and *Salamandra salamandra*
(chromatic dorsal pattern, its own measurements and a derived statistic) in
:func:`test_fire_salamander_workflow`.

Keep this test (and add to it) whenever a feature touches the cross-screen workflow.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest
from PIL import Image as PilImage

from herpetoid.api import ROI, ROIKind
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
from herpetoid.gui.widgets.observation_panel import observation_image_and_roi
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
    # Nothing is preselected in a fresh project: a species has to be chosen, as a user must.
    assert importer.selected_species() is None
    importer.species_combo.setCurrentText("Calotriton asper")
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

    # 10) Appearance: switching the style preset in Settings restyles the whole app live (the
    #     QApplication stylesheet now carries the preset's accent) and persists the choice.
    from PySide6.QtWidgets import QApplication

    from herpetoid.gui.screens.settings import SettingsScreen
    from herpetoid.gui.theme import get_style

    settings_screen = window.open_dialog("Settings")
    assert isinstance(settings_screen, SettingsScreen)
    app = QApplication.instance()
    assert app is not None
    settings_screen.style_combo.setCurrentIndex(settings_screen.style_combo.findData("slate"))
    assert state.settings.settings.style == "slate"
    assert get_style("slate").accent in app.styleSheet()
    # Restore the default so the shared QApplication doesn't leak the style into other tests.
    settings_screen.style_combo.setCurrentIndex(settings_screen.style_combo.findData("teal"))
    assert get_style("teal").accent in app.styleSheet()


# ---------------------------------------------------------------------------------------------
# A second species, with a different shape: colour instead of luminance, its own field sheet
# instead of a hand-drawn one, and its own measurements and statistics.
# ---------------------------------------------------------------------------------------------
_DORSUM = ((50, 90), (230, 55), (410, 95), (410, 185), (225, 230), (50, 190))


def _fire_salamander(seed: int) -> np.ndarray:
    """A black animal with a unique arrangement of yellow blotches, on leaf litter (RGB)."""
    rng = np.random.default_rng(seed)
    image = (
        rng.integers(70, 130, size=(280, 470, 1)).astype(np.uint8).repeat(3, axis=2)
        * np.array([1.0, 0.78, 0.5])
    ).astype(np.uint8)
    body = np.zeros(image.shape[:2], np.uint8)
    cv2.fillPoly(body, [np.array(_DORSUM, np.int32).reshape(-1, 1, 2)], 255)
    image[body > 0] = (28, 24, 22)
    for _ in range(rng.integers(14, 20)):
        blob = np.zeros(image.shape[:2], np.uint8)
        cv2.ellipse(
            blob,
            (int(rng.integers(80, 390)), int(rng.integers(95, 195))),
            (int(rng.integers(10, 25)), int(rng.integers(7, 17))),
            int(rng.integers(0, 180)),
            0,
            360,
            255,
            -1,
        )
        image[cv2.bitwise_and(blob, body) > 0] = (236, 196, 40)
    return cv2.GaussianBlur(image, (3, 3), 0)


def _rephotographed(image: np.ndarray) -> np.ndarray:
    """The same animal, a month later: different pose, different torchlight, different colour cast."""
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), 9.0, 1.04)
    out = cv2.warpAffine(image, matrix, (w, h), borderMode=cv2.BORDER_REFLECT).astype(np.float32)
    gradient = np.linspace(1.2, 0.5, w, dtype=np.float32)[None, :, None]
    return np.clip(out * gradient * np.array([1.22, 1.0, 0.74], np.float32), 0, 255).astype(np.uint8)


def test_fire_salamander_workflow(tmp_path: Path, qtbot) -> None:
    """The same shell, a species that works chromatically and proposes its own ROI."""
    cv2.setRNGSeed(23)
    registry = PluginRegistry()
    discover_entry_points(registry)
    settings = SettingsService(JsonSettingsStore(tmp_path / "settings.json"))
    state = AppState(
        registry=registry, project_service=ProjectService(app_version="e2e"), settings=settings
    )
    window = MainWindow(state)
    qtbot.addWidget(window)
    state.create_project(tmp_path / "fire", "Fire salamander transect")
    catalog = state.catalog
    assert catalog is not None

    # 1) The module is installed, so its species is offered for import — Core learned it from the
    #    registry, not from any hard-coded list.
    importer = window.open_dialog("Import")
    assert isinstance(importer, ImageImportScreen)
    species_names = [importer.species_combo.itemText(i) for i in range(importer.species_combo.count())]
    assert "Salamandra salamandra" in species_names
    importer.species_combo.setCurrentText("Salamandra salamandra")

    base = _fire_salamander(31)
    files = {
        "SS-base.png": base,
        "SS-recapture.png": _rephotographed(base),  # the same animal, re-photographed
        "SS-other.png": _fire_salamander(77),  # a different animal
    }
    for filename, picture in files.items():
        PilImage.fromarray(picture).save(tmp_path / filename)
    assert importer.import_files([tmp_path / name for name in files]) == 3

    def observation_id_for(filename: str) -> int:
        for observation in catalog.list_observations():
            assert observation.id is not None
            images = catalog.images_for(observation.id)
            if images and images[0].original_filename == filename:
                return observation.id
        raise AssertionError(f"no observation for {filename}")

    # 2) The editor adapts to what this species declares: a polygon tool, its own guidance and its
    #    own measurement fields.
    editor = window.find_screen(ObservationsScreen)
    assert isinstance(editor, ObservationsScreen)
    ids = {name: observation_id_for(name) for name in files}
    editor.select_observation(ids["SS-base.png"])
    assert editor.draw_button.text() == "Draw polygon"
    assert "dorsal pattern" in editor.guidance_label.text()
    assert editor._form is not None
    assert {"svl", "weight", "pattern_type"} <= editor._form.values().keys()

    # 3) Mark the dorsum on each capture with the polygon tool, then record the field data.
    measurements = {
        "SS-base.png": {"svl": 92.0, "weight": 31.0, "pattern_type": "spotted"},
        "SS-recapture.png": {"svl": 95.0, "weight": 34.0, "pattern_type": "spotted"},
        "SS-other.png": {"svl": 78.0, "weight": 19.0, "pattern_type": "striped"},
    }
    codes = {"SS-base.png": "SS-001", "SS-recapture.png": "SS-002", "SS-other.png": "SS-003"}
    for filename, observation_id in ids.items():
        editor.select_observation(observation_id)
        editor.viewer.set_roi(ROI(kind=ROIKind.POLYGON, points=_DORSUM))
        marked = editor.viewer.roi()
        assert marked is not None, f"no region marked for {filename}"
        assert marked.kind is ROIKind.POLYGON
        editor.code_edit.setText(codes[filename])
        editor.observer_edit.setText("AL")
        assert editor._form is not None
        editor._form.set_values(measurements[filename])
        editor.save()
        assert "saved successfully" in editor.toast.text()
    assert len(catalog.comparable_observations()) == 3  # all three carry a ROI

    # 4) Identify: enrol the recapture and the other animal, then query the base capture. The
    #    module's chromatic pattern map has to put the true recapture first.
    identification = window.find_screen(IdentificationScreen)
    assert isinstance(identification, IdentificationScreen)
    identification.algorithm_combo.setCurrentIndex(identification.algorithm_combo.findData("orb"))
    for filename in ("SS-recapture.png", "SS-other.png"):
        identification.query_combo.setCurrentIndex(
            identification.query_combo.findData(ids[filename])
        )
        identification.identify()
        if identification._first_mark_button is not None:  # the project's very first individual
            identification._first_mark_button.click()
        else:
            identification.mark_new()
    assert {i.code for i in catalog.list_individuals()} == {"SS-002", "SS-003"}

    identification.query_combo.setCurrentIndex(
        identification.query_combo.findData(ids["SS-base.png"])
    )
    identification.identify()
    assert identification._candidates, "identification returned no candidates"
    assert identification._candidates[0].observation.id == ids["SS-recapture.png"], (
        "the re-photographed animal must outrank the different one"
    )
    identification.confirm_same()
    linked = catalog.get_observation(ids["SS-base.png"])
    recapture = catalog.get_observation(ids["SS-recapture.png"])
    assert linked is not None and recapture is not None
    assert linked.individual_id == recapture.individual_id
    assert catalog.individual_count() == 2

    # 5) Statistics are built from what this species declares — including a derived metric Core
    #    knows nothing about (Fulton's K = 10^5 * weight / SVL^3) and its own categorical field.
    statistics = window.find_screen(StatisticsScreen)
    assert isinstance(statistics, StatisticsScreen)
    statistics._refresh()
    rows = {
        statistics.table.item(r, 0).text(): statistics.table.item(r, 1).text()
        for r in range(statistics.table.rowCount())
    }
    assert "Observations: 3" in statistics.summary_label.text()
    assert rows["Mean SVL (mm)"] == "88.33"
    assert rows["Dorsal pattern types"] == "spotted: 1, striped: 1"  # per individual, latest value
    # The module's pure callable is applied per observation and then averaged by the engine.
    expected_k = float(
        np.mean([1e5 * weight / svl**3 for svl, weight in ((92.0, 31.0), (95.0, 34.0), (78.0, 19.0))])
    )
    assert float(rows["Mean body condition (Fulton's K)"]) == pytest.approx(expected_k, abs=0.005)


def test_folder_import_fills_dates_across_screens(tmp_path: Path, qtbot, monkeypatch) -> None:
    """A season's folder tree goes in as one selection, and each capture keeps the date its path states.

    This is the whole point of the two features together: the researcher picks the session folder
    once, and the Date cell they would otherwise fill in by hand — for every photograph — is already
    right, written day-first, and survives a save.
    """
    from datetime import date

    from PySide6.QtWidgets import QFileDialog, QMessageBox

    registry = PluginRegistry()
    discover_entry_points(registry)
    settings = SettingsService(JsonSettingsStore(tmp_path / "settings.json"))
    state = AppState(
        registry=registry, project_service=ProjectService(app_version="e2e"), settings=settings
    )
    window = MainWindow(state)
    qtbot.addWidget(window)
    state.create_project(tmp_path / "proj", "Season 2023")
    catalog = state.catalog
    assert catalog is not None

    # 1) A realistic card dump: one dated session folder, a camera subfolder per device, and a file
    #    whose own name carries a different (later) date than the folder it sits in.
    session = tmp_path / "field" / "2023-07-15 Riu Aigues"
    photos = {
        session / "CAM1" / "DSC_0001.png": date(2023, 7, 15),  # date from the session folder
        session / "CAM1" / "deep" / "DSC_0002.png": date(2023, 7, 15),  # ...however deep it sits
        session / "CAM2" / "IMG_20230716_0031.png": date(2023, 7, 16),  # the file name wins
    }
    for index, path in enumerate(photos):
        path.parent.mkdir(parents=True, exist_ok=True)
        _save(path, _spots(index + 1))
    # ...plus one straight off the card, in a folder that states nothing: only its EXIF knows.
    from_card = tmp_path / "field" / "DCIM" / "100CANON" / "DSC_0099.jpg"
    from_card.parent.mkdir(parents=True, exist_ok=True)
    exif = PilImage.Exif()
    exif.get_ifd(0x8769)[0x9003] = "2023:07:17 22:10:04"  # DateTimeOriginal
    PilImage.fromarray(np.stack([_spots(4)] * 3, axis=-1)).save(from_card, "JPEG", exif=exif)
    (session / "CAM1" / "field-notes.txt").write_text("not a photograph", encoding="utf-8")
    (tmp_path / "field" / "elsewhere.png").parent.mkdir(parents=True, exist_ok=True)
    _save(tmp_path / "field" / "elsewhere.png", _spots(9))  # outside the chosen folder

    # 2) Select the session folder once — every image below it is staged, nothing else is.
    importer = window.open_dialog("Import")
    assert isinstance(importer, ImageImportScreen)
    importer.species_combo.setCurrentText("Calotriton asper")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(session))
    importer._choose_folder()
    assert sorted(importer.staged_files()) == sorted(photos)

    # The card folder is a second selection; both trees end up in the one staging strip.
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(from_card.parent))
    importer._choose_folder()
    photos[from_card] = date(2023, 7, 17)
    assert sorted(importer.staged_files()) == sorted(photos)

    importer.observer_edit.setText("AL")
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    importer._import_staged()
    assert catalog.observation_count() == 4
    assert importer.staged_files() == []

    # 3) Every observation arrived with the date its path stated.
    by_filename = {
        catalog.images_for(obs.id)[0].original_filename: obs
        for obs in catalog.list_observations()
        if obs.id is not None
    }
    for path, expected in photos.items():
        observation = by_filename[path.name]
        assert observation.observed_at is not None, f"{path.name} imported without a date"
        assert observation.observed_at.date() == expected

    # 4) The Observations tab shows it day-first, in the cell the researcher would have typed into.
    editor = window.find_screen(ObservationsScreen)
    assert isinstance(editor, ObservationsScreen)
    assert editor.date_edit.displayFormat() == "dd/MM/yyyy"
    later = by_filename["IMG_20230716_0031.png"]
    assert later.id is not None
    editor.select_observation(later.id)
    assert editor.date_edit.date().toString("dd/MM/yyyy") == "16/07/2023"

    # 5) Saving the observation keeps that date — it is not quietly replaced with today's.
    editor.code_edit.setText("CA-101")
    editor.viewer.set_roi(ROI.rectangle(10, 10, 236, 236))
    editor.save()
    reloaded = catalog.get_observation(later.id)
    assert reloaded is not None and reloaded.observed_at is not None
    assert reloaded.observed_at.date() == date(2023, 7, 16)

    # 6) ...and once the capture belongs to an individual, the catalog browser writes it the same way.
    individual = catalog.create_individual(reloaded.species_id, code="CA-101")
    assert individual.id is not None
    catalog.link_observation(later.id, individual.id)
    state.project_changed.emit()
    browser = window.find_screen(IndividualBrowserScreen)
    assert isinstance(browser, IndividualBrowserScreen)
    browser.table.selectRow(0)
    assert "16/07/2023" in browser.obs_position_label.text()


def test_a_project_imported_under_the_wrong_species_is_corrected_in_place(
    tmp_path: Path, qtbot
) -> None:
    """Fire salamanders filed as brook newts, caught mid-project and corrected without re-importing.

    This is the whole answer to "does the species matter?": the module decides which fields exist,
    how the pattern is read and what a capture is compared against. So the correction has to carry
    the photographs, the marked regions and the recorded values across intact — and leave a project
    that identifies correctly under the right module.
    """
    cv2.setRNGSeed(17)
    registry = PluginRegistry()
    discover_entry_points(registry)
    settings = SettingsService(JsonSettingsStore(tmp_path / "settings.json"))
    state = AppState(
        registry=registry, project_service=ProjectService(app_version="e2e"), settings=settings
    )
    window = MainWindow(state)
    qtbot.addWidget(window)
    state.create_project(tmp_path / "proj", "Wrong species")
    catalog = state.catalog
    assert catalog is not None

    # 1) The mistake: fire salamanders imported as Calotriton asper.
    base = _fire_salamander(5)
    files = {
        "SS-base.png": base,
        "SS-recapture.png": _rephotographed(base),
        "SS-other.png": _fire_salamander(88),
    }
    for filename, picture in files.items():
        PilImage.fromarray(picture).save(tmp_path / filename)
    importer = window.open_dialog("Import")
    assert isinstance(importer, ImageImportScreen)
    importer.species_combo.setCurrentText("Calotriton asper")
    importer.observer_edit.setText("AL")
    assert importer.import_files([tmp_path / name for name in files]) == 3
    assert "Calotriton asper" in window._species_status.text()

    # 2) It shows: the editor offers the newt's fields, and the newt's guidance.
    editor = window.find_screen(ObservationsScreen)
    assert isinstance(editor, ObservationsScreen)
    ids = sorted(o.id for o in catalog.list_observations() if o.id is not None)
    editor.select_observation(ids[0])
    assert editor.species_label.text() == "Calotriton asper"
    assert editor._form is not None
    assert "pattern_type" not in editor._form.values()  # a fire salamander field, absent
    assert "ventral" in editor.guidance_label.text()

    # 3) Work already done under the wrong species must survive the correction: marked regions,
    #    measurements, and the individual codes typed in but not yet confirmed.
    codes = dict(zip(ids, ("SS-001", "SS-002", "SS-003"), strict=True))
    for observation_id in ids:
        editor.select_observation(observation_id)
        editor.viewer.set_roi(ROI(kind=ROIKind.POLYGON, points=_DORSUM))
        editor.observer_edit.setText("AL")
        editor.code_edit.setText(codes[observation_id])
        assert editor._form is not None
        editor._form.set_values({"svl": 91.0, "weight": 30.0})
        editor.save()
    assert len(catalog.comparable_observations()) == 3

    # 4) The fix, from the Observations tab — where the wrong species is on screen.
    dialog = editor.open_change_species()
    qtbot.addWidget(dialog)
    dialog.to_combo.setCurrentText("Salamandra salamandra")
    dialog.scope_combo.setCurrentIndex(dialog.scope_combo.findData("all"))
    assert dialog.observation_ids() == ids
    report = dialog.apply_change()
    assert report is not None and report.observations == 3

    # 5) The project stops claiming a species it no longer holds, and the editor follows.
    assert [s.scientific_name for s in catalog.list_species()] == ["Salamandra salamandra"]
    assert "Salamandra salamandra" in window._species_status.text()
    editor.select_observation(ids[0])
    assert editor.species_label.text() == "Salamandra salamandra"
    assert editor._form is not None
    assert {"pattern_type", "total_length"} <= editor._form.values().keys()  # its own fields now
    assert "dorsal" in editor.guidance_label.text()  # ...and its own ROI guidance
    assert editor._form.values()["svl"] == 91.0  # what was measured carries over
    assert len(catalog.comparable_observations()) == 3  # every marked region survived
    moved = {o.id: o for o in catalog.list_observations()}
    assert {pending_code(moved[i]) for i in ids} == set(codes.values())  # codes came too

    # 6) The corrected project identifies under the right module: enrol two, query the third, and
    #    the re-photographed animal must outrank the different one.
    identification = window.find_screen(IdentificationScreen)
    assert isinstance(identification, IdentificationScreen)
    identification.algorithm_combo.setCurrentIndex(identification.algorithm_combo.findData("orb"))
    by_name = {
        catalog.images_for(o.id)[0].original_filename: o.id
        for o in catalog.list_observations()
        if o.id is not None
    }
    for filename in ("SS-recapture.png", "SS-other.png"):
        index = identification.query_combo.findData(by_name[filename])
        assert index >= 0, f"{filename} is not selectable as a query (combo not refreshed?)"
        identification.query_combo.setCurrentIndex(index)
        identification.identify()
        if identification._first_mark_button is not None:
            identification._first_mark_button.click()
        else:
            identification.mark_new()
    assert catalog.individual_count() == 2, "enrolling the two catalog animals did not create them"
    identification.query_combo.setCurrentIndex(
        identification.query_combo.findData(by_name["SS-base.png"])
    )
    identification.identify()
    assert identification._candidates, "identification returned no candidates after the move"
    assert identification._candidates[0].observation.id == by_name["SS-recapture.png"]
    # The codes typed before the correction became the real individuals after it.
    assert {i.code for i in catalog.list_individuals()} == {"SS-002", "SS-003"}


def test_turning_a_capture_travels_with_it_into_identification(tmp_path: Path, qtbot) -> None:
    """A capture turned upright in the editor is turned everywhere — matcher included.

    Two animals photographed head-to-tail are hard to judge side by side. Correcting one has to reach
    the identification views, or the reviewer is comparing something the software is not.
    """
    cv2.setRNGSeed(29)
    registry = PluginRegistry()
    discover_entry_points(registry)
    settings = SettingsService(JsonSettingsStore(tmp_path / "settings.json"))
    state = AppState(
        registry=registry, project_service=ProjectService(app_version="e2e"), settings=settings
    )
    window = MainWindow(state)
    qtbot.addWidget(window)
    state.create_project(tmp_path / "proj", "Turned")
    catalog = state.catalog
    assert catalog is not None

    base = _spots(41)
    files = {"a.png": base, "b.png": _rotate(base, 8), "c.png": _spots(404)}
    for filename, gray in files.items():
        _save(tmp_path / filename, gray)
    importer = window.open_dialog("Import")
    assert isinstance(importer, ImageImportScreen)
    importer.species_combo.setCurrentText("Calotriton asper")
    importer.observer_edit.setText("AL")
    assert importer.import_files([tmp_path / name for name in files]) == 3

    editor = window.find_screen(ObservationsScreen)
    assert isinstance(editor, ObservationsScreen)
    ids = {
        catalog.images_for(o.id)[0].original_filename: o.id
        for o in catalog.list_observations()
        if o.id is not None
    }
    codes = {"a.png": "CA-001", "b.png": "CA-002", "c.png": "CA-003"}
    for filename, observation_id in ids.items():
        editor.select_observation(observation_id)
        editor.viewer.set_roi(ROI.rectangle(10, 10, 236, 236))
        editor.observer_edit.setText("AL")
        editor.code_edit.setText(codes[filename])
        editor.save()

    # Turn one capture a quarter turn in the editor, as the researcher would for a head-down animal.
    editor.select_observation(ids["b.png"])
    editor.rotate_current_image(90)
    turned_image = catalog.images_for(ids["b.png"])[0]
    assert turned_image.rotation == 90
    assert turned_image.id is not None

    # The whole application now agrees on which way up it is.
    array, roi = observation_image_and_roi(state, ids["b.png"])
    assert array is not None and roi is not None
    stored = catalog.get_image_roi(turned_image.id)
    assert stored is not None
    assert roi.bounding_box() != stored.bounding_box()  # the view turned it; the bundle did not

    # And the matcher works on that same turned picture: the true recapture still ranks first.
    identification = window.find_screen(IdentificationScreen)
    assert isinstance(identification, IdentificationScreen)
    identification.algorithm_combo.setCurrentIndex(identification.algorithm_combo.findData("orb"))
    for filename in ("b.png", "c.png"):
        identification.query_combo.setCurrentIndex(
            identification.query_combo.findData(ids[filename])
        )
        identification.identify()
        if identification._first_mark_button is not None:
            identification._first_mark_button.click()
        else:
            identification.mark_new()
    identification.query_combo.setCurrentIndex(identification.query_combo.findData(ids["a.png"]))
    identification.identify()
    assert identification._candidates, "no candidates after turning a capture"
    assert identification._candidates[0].observation.id == ids["b.png"], (
        "the turned recapture must still outrank the different animal"
    )

    # Reopening the bundle keeps the turn: it is stored, not a property of this session's view.
    state.close_project()
    state.open_project(tmp_path / "proj")
    reopened = state.catalog
    assert reopened is not None
    assert reopened.images_for(ids["b.png"])[0].rotation == 90
