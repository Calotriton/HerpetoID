"""GUI tests (headless via the offscreen Qt platform + pytest-qt)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PySide6.QtCore import Qt

from herpetoid.application.project_service import ProjectService
from herpetoid.application.registry import PluginRegistry
from herpetoid.application.settings import SettingsService
from herpetoid.gui.main_window import MainWindow
from herpetoid.gui.screens.plugins import PluginManagerScreen
from herpetoid.gui.screens.projects import ProjectManagerScreen
from herpetoid.gui.state import AppState
from herpetoid.gui.widgets.image_viewer import ImageViewer, ndarray_to_qimage
from herpetoid.infrastructure.plugin_discovery import discover_entry_points
from herpetoid.infrastructure.settings_store import JsonSettingsStore

pytestmark = pytest.mark.gui


def _write_image(path: Path, size: int = 16) -> Path:
    """A tiny real image on disk — enough for anything that only needs a decodable file."""
    from PIL import Image as PilImage

    PilImage.fromarray(np.zeros((size, size, 3), np.uint8)).save(path)
    return path


@pytest.fixture
def app_state(tmp_path: Path, qtbot) -> AppState:
    registry = PluginRegistry()
    discover_entry_points(registry)
    settings = SettingsService(JsonSettingsStore(tmp_path / "settings.json"))
    return AppState(
        registry=registry,
        project_service=ProjectService(app_version="test"),
        settings=settings,
    )


def test_ndarray_to_qimage(qtbot) -> None:
    gray = ndarray_to_qimage(np.zeros((10, 12), np.uint8))
    assert (gray.width(), gray.height()) == (12, 10)
    rgb = ndarray_to_qimage(np.zeros((10, 12, 3), np.uint8))
    assert (rgb.width(), rgb.height()) == (12, 10)


def test_image_viewer_set_and_zoom(qtbot) -> None:
    viewer = ImageViewer()
    qtbot.addWidget(viewer)
    assert not viewer.has_image()
    viewer.set_image(np.random.default_rng(0).integers(0, 256, (64, 80), dtype=np.uint8))
    assert viewer.has_image()
    before = viewer.current_scale()
    viewer.zoom(2.0)
    zoomed_in = viewer.current_scale()
    assert zoomed_in > before
    viewer.zoom(1 / 2.0)  # scrolling the other way must zoom back out
    assert viewer.current_scale() < zoomed_in


def test_main_window_navigation(app_state: AppState, qtbot) -> None:
    from herpetoid.gui.screens.identification import IdentificationScreen

    window = MainWindow(app_state)
    qtbot.addWidget(window)
    assert window.screen_names() == [
        "Dashboard",
        "Observations",
        "Individuals",
        "Identification",
        "Statistics",
    ]
    assert window.current_screen_name() == "Dashboard"
    window.navigate_to("Observations")
    assert window.current_screen_name() == "Observations"

    # Legacy names still work: Home -> Dashboard tab; Candidates/Comparison -> the merged
    # Identification tab in the right mode; secondary screens open as dialogs (tab unchanged).
    window.navigate_to("Home")
    assert window.current_screen_name() == "Dashboard"
    window.navigate_to("Comparison")
    assert window.current_screen_name() == "Identification"
    assert window.find_screen(IdentificationScreen).mode() == "compare"
    window.navigate_to("Candidates")
    assert window.find_screen(IdentificationScreen).mode() == "identify"
    window.navigate_to("Plugins")
    assert window.current_screen_name() == "Identification"  # dialogs don't switch tabs
    assert isinstance(window.open_dialog("Plugins"), PluginManagerScreen)


def test_main_window_menus_corner_button_and_dialogs(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    from herpetoid.gui.screens.identification import IdentificationScreen
    from herpetoid.gui.screens.import_images import ImageImportScreen
    from herpetoid.gui.screens.settings import SettingsScreen

    window = MainWindow(app_state)
    qtbot.addWidget(window)

    # One command surface: the menus (the old icon toolbar only duplicated them). The Plugin
    # Manager lives under Tools rather than a one-item top-level menu.
    menus = [a.text().replace("&", "") for a in window.menuBar().actions()]
    assert menus == ["File", "Project", "View", "Tools", "Help"]
    tools_texts = [a.text() for a in window._tools_menu.actions()]
    assert tools_texts == ["Settings…", "Plugin Manager…"]

    # Dialogs host the secondary screens and are cached (same instance on re-open).
    settings_screen = window.open_dialog("Settings")
    assert isinstance(settings_screen, SettingsScreen)
    assert window.open_dialog("Settings") is settings_screen
    assert isinstance(window.open_dialog("Import"), ImageImportScreen)
    assert isinstance(window.open_dialog("Projects"), ProjectManagerScreen)

    # Project-dependent actions (and the corner Add Observations button on the tab row) are
    # disabled without a project and enabled with one.
    assert not window._import_action.isEnabled()
    assert not window.import_button.isEnabled()
    assert window._tabs.cornerWidget(Qt.Corner.TopRightCorner) is not None
    app_state.create_project(tmp_path / "proj", "P")
    assert window._import_action.isEnabled()
    assert window._identify_action.isEnabled()
    assert window.import_button.isEnabled()
    window._dialogs["Import"].hide()
    window.import_button.click()  # the corner button opens the Import dialog
    assert window._dialogs["Import"].isVisible()

    # The Recent Projects submenu lists the (still-existing) bundle.
    window._rebuild_recent_menu()
    recent_texts = [a.text() for a in window._recent_menu.actions()]
    assert any("proj" in t for t in recent_texts)

    # The algorithm is chosen in exactly one place — the Identification tab — and the pick is
    # persisted as the default that fresh screens pre-select.
    identification = window.find_screen(IdentificationScreen)
    assert isinstance(identification, IdentificationScreen)
    assert identification.algorithm_combo.count() >= 1
    identification._on_algorithm_changed()  # what the combo's change signal invokes
    picked = identification.algorithm_combo.currentData()
    assert app_state.settings.settings.default_algorithm_id == picked
    fresh = IdentificationScreen(app_state)
    qtbot.addWidget(fresh)
    assert fresh.algorithm_combo.currentData() == picked

    # Close Project via state clears the window title back to the default.
    app_state.close_project()
    assert window.windowTitle() == "HerpetoID"
    assert not window._import_action.isEnabled()
    assert not window.import_button.isEnabled()


def test_main_window_dock_and_theme_action(app_state: AppState, tmp_path: Path, qtbot) -> None:
    from PIL import Image as PilImage

    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.individuals import IndividualBrowserScreen
    from herpetoid.gui.screens.observations import ObservationsScreen

    window = MainWindow(app_state)
    qtbot.addWidget(window)

    assert "No project open" in window._dock.tree.topLevelItem(0).text(0)
    app_state.create_project(tmp_path / "proj", "DockStudy")
    root = window._dock.tree.topLevelItem(0)
    assert root.text(0) == "DockStudy"
    children = [root.child(i).text(0) for i in range(root.childCount())]
    assert "Observations (0)" in children
    assert "Individuals (0)" in children
    assert "Individuals: 0" in window._dock.stats_label.text()

    # The tree lists the actual records; activating one jumps to the tab with it selected.
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    image = tmp_path / "i.png"
    PilImage.fromarray(np.zeros((16, 16, 3), np.uint8)).save(image)
    obs = catalog.import_observation(species.id, [image])
    individual = catalog.create_individual(species.id, code="CA-042")
    app_state.project_changed.emit()

    root = window._dock.tree.topLevelItem(0)
    obs_group = next(
        root.child(i) for i in range(root.childCount()) if "Observations" in root.child(i).text(0)
    )
    assert obs_group.childCount() == 1
    window._dock._on_item_activated(obs_group.child(0))
    assert window.current_screen_name() == "Observations"
    assert window.find_screen(ObservationsScreen)._current.id == obs.id

    ind_group = next(
        root.child(i) for i in range(root.childCount()) if "Individuals" in root.child(i).text(0)
    )
    assert ind_group.child(0).text(0) == "CA-042"
    window._dock._on_item_activated(ind_group.child(0))
    assert window.current_screen_name() == "Individuals"
    individuals_screen = window.find_screen(IndividualBrowserScreen)
    assert individuals_screen._individuals[individuals_screen.table.currentRow()].id == individual.id

    # The View menu's toggle action hides/shows the dock (needs a shown window to have effect).
    window.show()
    toggle = window._dock.toggleViewAction()
    assert window._dock.isVisible()
    toggle.trigger()
    assert not window._dock.isVisible()
    toggle.trigger()
    assert window._dock.isVisible()

    # The theme menu action persists the choice in settings.
    window._set_theme("dark")
    assert app_state.settings.settings.theme == "dark"
    window._set_theme("light")
    assert app_state.settings.settings.theme == "light"


def test_plugin_manager_shows_registered_plugins(app_state: AppState, qtbot) -> None:
    screen = PluginManagerScreen(app_state.registry)
    qtbot.addWidget(screen)
    assert screen.modules_table.rowCount() >= 1
    assert screen.algorithms_table.rowCount() >= 1


def test_create_project_updates_state(app_state: AppState, tmp_path: Path, qtbot) -> None:
    bundle = tmp_path / "study"
    app_state.create_project(bundle, "P1")
    assert app_state.project is not None
    assert app_state.project.project.name == "P1"
    assert (bundle / "project.db").exists()
    assert app_state.settings.settings.recent_projects == [str(bundle)]


def test_project_manager_screen_reflects_open_project(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    screen = ProjectManagerScreen(app_state)
    qtbot.addWidget(screen)
    assert "No project open" in screen.current_label.text()
    app_state.create_project(tmp_path / "p2", "P2")  # emits project_changed -> screen refreshes
    assert "P2" in screen.current_label.text()
    assert screen.recent_list.count() == 1


def test_main_window_title_tracks_project(app_state: AppState, tmp_path: Path, qtbot) -> None:
    window = MainWindow(app_state)
    qtbot.addWidget(window)
    assert window.windowTitle() == "HerpetoID"
    app_state.create_project(tmp_path / "p3", "Pyrenees")
    assert "Pyrenees" in window.windowTitle()


def test_image_import_creates_observation(app_state: AppState, tmp_path: Path, qtbot) -> None:
    from PIL import Image as PilImage

    from herpetoid.gui.screens.import_images import ImageImportScreen

    app_state.create_project(tmp_path / "proj", "P")
    screen = ImageImportScreen(app_state)
    screen.species_combo.setCurrentText("Calotriton asper")  # never defaulted now
    qtbot.addWidget(screen)
    assert screen.selected_species() == "Calotriton asper"

    source = tmp_path / "newt.png"
    PilImage.fromarray(np.zeros((32, 32, 3), np.uint8)).save(source)
    assert screen.import_files([source]) == 1

    catalog = app_state.catalog
    assert catalog is not None
    assert catalog.observation_count() == 1
    assert list((tmp_path / "proj" / "images").glob("*"))
    assert screen.gallery.count() == 1  # imported image appears as a thumbnail


def test_import_refreshes_other_screens(app_state: AppState, tmp_path: Path, qtbot) -> None:
    """Screens created before importing (as in the real window) must update after an import."""
    from PIL import Image as PilImage

    from herpetoid.gui.screens.identification import IdentificationScreen
    from herpetoid.gui.screens.import_images import ImageImportScreen
    from herpetoid.gui.screens.observations import ObservationsScreen

    app_state.create_project(tmp_path / "proj", "P")
    observations = ObservationsScreen(app_state)
    candidates = IdentificationScreen(app_state)
    importer = ImageImportScreen(app_state)
    importer.species_combo.setCurrentText("Calotriton asper")  # never defaulted now
    for widget in (observations, candidates, importer):
        qtbot.addWidget(widget)

    assert observations.table.rowCount() == 0  # empty before import
    assert candidates.query_combo.count() == 0

    source = tmp_path / "a.png"
    PilImage.fromarray(np.zeros((32, 32, 3), np.uint8)).save(source)
    importer.import_files([source])

    assert observations.table.rowCount() == 1  # refreshed via project_changed
    # A freshly imported observation is not yet comparable (no individual, no ROI).
    assert candidates.query_combo.count() == 0

    from herpetoid.api import ROI

    catalog = app_state.catalog
    assert catalog is not None
    obs = catalog.list_observations()[0]
    species = catalog.list_species()[0]
    assert obs.id is not None and species.id is not None
    individual = catalog.create_individual(species.id)
    catalog.link_observation(obs.id, individual.id)
    image = catalog.images_for(obs.id)[0]
    assert image.id is not None
    catalog.set_image_roi(image.id, ROI.rectangle(2, 2, 20, 20))
    app_state.project_changed.emit()

    # Now that it is an individual with a marked ROI, it becomes selectable for identification.
    assert candidates.query_combo.count() == 1


def test_import_observer_gating_and_delete(
    app_state: AppState, tmp_path: Path, qtbot, monkeypatch
) -> None:
    from PIL import Image as PilImage
    from PySide6.QtWidgets import QMessageBox

    from herpetoid.gui.screens.import_images import ImageImportScreen

    app_state.create_project(tmp_path / "proj", "P")
    screen = ImageImportScreen(app_state)
    screen.species_combo.setCurrentText("Calotriton asper")  # never defaulted now
    qtbot.addWidget(screen)

    a, b = tmp_path / "a.png", tmp_path / "b.png"
    for path in (a, b):
        PilImage.fromarray(np.zeros((16, 16, 3), np.uint8)).save(path)
    catalog = app_state.catalog
    assert catalog is not None

    # Two-step import: selecting stages the files only; nothing enters the project until the
    # explicit Import press — and Import is gated on an observer name.
    screen.stage_files([a, b])
    assert screen.staged_files() == [a, b]
    assert catalog.observation_count() == 0  # staged, not imported
    assert not screen.import_button.isEnabled()  # no observer yet
    screen.observer_edit.setText("AL")
    assert screen.import_button.isEnabled()
    assert "2" in screen.import_button.text()

    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    screen._import_staged()
    assert catalog.observation_count() == 2
    assert screen.staged_files() == []  # staging area cleared after a successful import
    assert screen.gallery.count() == 2

    # Select all and delete (auto-confirm the dialog); the observations are removed.
    monkeypatch.setattr(
        QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes
    )
    screen.gallery.selectAll()
    assert screen.delete_button.isEnabled()
    screen._delete_selected()
    assert catalog.observation_count() == 0
    assert screen.gallery.count() == 0


def test_folder_selection_stages_every_image_in_the_subfolders(
    app_state: AppState, tmp_path: Path, qtbot, monkeypatch
) -> None:
    """Selecting one session folder must stage the whole tree under it, not just its top level."""
    from PIL import Image as PilImage
    from PySide6.QtWidgets import QFileDialog

    from herpetoid.gui.screens.import_images import ImageImportScreen

    app_state.create_project(tmp_path / "proj", "P")
    screen = ImageImportScreen(app_state)
    screen.species_combo.setCurrentText("Calotriton asper")  # never defaulted now
    qtbot.addWidget(screen)

    session = tmp_path / "2023-07-15 Riu Aigues"
    images = [
        session / "top.jpg",
        session / "CAM1" / "a.jpg",
        session / "CAM1" / "b.png",
        session / "CAM2" / "deep" / "c.jpg",
    ]
    for path in images:
        path.parent.mkdir(parents=True, exist_ok=True)
        PilImage.fromarray(np.zeros((16, 16, 3), np.uint8)).save(path)
    (session / "CAM1" / "field-notes.txt").write_text("not an image", encoding="utf-8")

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(session))
    screen._choose_folder()

    assert sorted(screen.staged_files()) == sorted(images)
    assert screen.staged_list.count() == 4
    assert "4" in screen.import_button.text()
    # Selecting the same folder again adds nothing: the strip never grows duplicates.
    screen._choose_folder()
    assert len(screen.staged_files()) == 4


def test_folder_selection_reports_an_empty_folder(
    app_state: AppState, tmp_path: Path, qtbot, monkeypatch
) -> None:
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from herpetoid.gui.screens.import_images import ImageImportScreen

    app_state.create_project(tmp_path / "proj", "P")
    screen = ImageImportScreen(app_state)
    screen.species_combo.setCurrentText("Calotriton asper")  # never defaulted now
    qtbot.addWidget(screen)

    empty = tmp_path / "no photos here"
    (empty / "sub").mkdir(parents=True)
    (empty / "sub" / "notes.txt").write_text("nothing", encoding="utf-8")

    messages: list[str] = []
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *a, **k: str(empty))
    monkeypatch.setattr(
        QMessageBox, "information", lambda _p, _t, text, *a, **k: messages.append(text)
    )
    screen._choose_folder()

    assert screen.staged_files() == []
    assert messages and "no supported image files" in messages[0]


def test_import_fills_the_date_from_the_file_name_or_its_folder(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    """A date written in the path is read into the observation, so it needn't be typed per photo."""
    from datetime import date

    from PIL import Image as PilImage

    from herpetoid.gui.screens.import_images import ImageImportScreen

    app_state.create_project(tmp_path / "proj", "P")
    screen = ImageImportScreen(app_state)
    screen.species_combo.setCurrentText("Calotriton asper")  # never defaulted now
    qtbot.addWidget(screen)
    catalog = app_state.catalog
    assert catalog is not None

    named = tmp_path / "session" / "IMG_20230715_142530.jpg"  # date in the file name
    foldered = tmp_path / "15-07-2023 Riu Aigues" / "CAM1" / "DSC_0001.jpg"  # date in a folder
    undated = tmp_path / "session" / "DSC_0002.jpg"  # nothing to go on
    for path in (named, foldered, undated):
        path.parent.mkdir(parents=True, exist_ok=True)
        PilImage.fromarray(np.zeros((16, 16, 3), np.uint8)).save(path)

    # An untouched card dump: the path says nothing, so the camera's own EXIF answers.
    from_card = tmp_path / "DCIM" / "100CANON" / "DSC_0031.jpg"
    from_card.parent.mkdir(parents=True, exist_ok=True)
    exif = PilImage.Exif()
    exif.get_ifd(0x8769)[0x9003] = "2023:07:20 14:25:30"  # DateTimeOriginal
    PilImage.fromarray(np.zeros((16, 16, 3), np.uint8)).save(from_card, "JPEG", exif=exif)

    assert screen.import_files([named, foldered, undated, from_card]) == 4
    dates = {
        catalog.images_for(obs.id)[0].original_filename: obs.observed_at
        for obs in catalog.list_observations()
        if obs.id is not None
    }
    assert dates["IMG_20230715_142530.jpg"].date() == date(2023, 7, 15)
    assert dates["DSC_0001.jpg"].date() == date(2023, 7, 15)
    assert dates["DSC_0031.jpg"].date() == date(2023, 7, 20)  # from EXIF
    assert dates["DSC_0002.jpg"] is None  # never guessed


def test_staged_tooltip_shows_the_detected_date_day_first(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    from PIL import Image as PilImage

    from herpetoid.gui.screens.import_images import ImageImportScreen

    app_state.create_project(tmp_path / "proj", "P")
    screen = ImageImportScreen(app_state)
    screen.species_combo.setCurrentText("Calotriton asper")  # never defaulted now
    qtbot.addWidget(screen)

    dated = tmp_path / "2023-07-15" / "a.jpg"
    plain = tmp_path / "b.jpg"
    for path in (dated, plain):
        path.parent.mkdir(parents=True, exist_ok=True)
        PilImage.fromarray(np.zeros((16, 16, 3), np.uint8)).save(path)

    carded = tmp_path / "DCIM" / "DSC_0031.jpg"
    carded.parent.mkdir(parents=True, exist_ok=True)
    exif = PilImage.Exif()
    exif.get_ifd(0x8769)[0x9003] = "2023:07:20 14:25:30"  # DateTimeOriginal
    PilImage.fromarray(np.zeros((16, 16, 3), np.uint8)).save(carded, "JPEG", exif=exif)

    screen.stage_files([dated, plain, carded])
    assert "Date from file name/folder: 15/07/2023" in screen.staged_list.item(0).toolTip()
    assert screen.staged_list.item(1).toolTip() == str(plain)  # no date anywhere: just the path
    assert "Date from camera (EXIF): 20/07/2023" in screen.staged_list.item(2).toolTip()


def test_import_skips_unreadable_files_and_keeps_the_rest(
    app_state: AppState, tmp_path: Path, qtbot, monkeypatch
) -> None:
    """One corrupt file off a camera card must not cost the researcher the whole batch."""
    from PIL import Image as PilImage
    from PySide6.QtWidgets import QMessageBox

    from herpetoid.gui.screens.import_images import ImageImportScreen

    app_state.create_project(tmp_path / "proj", "P")
    screen = ImageImportScreen(app_state)
    screen.species_combo.setCurrentText("Calotriton asper")  # never defaulted now
    qtbot.addWidget(screen)
    catalog = app_state.catalog
    assert catalog is not None

    good_a, bad, good_b = tmp_path / "a.png", tmp_path / "truncated.png", tmp_path / "b.png"
    for path in (good_a, good_b):
        PilImage.fromarray(np.zeros((16, 16, 3), np.uint8)).save(path)
    bad.write_bytes(b"\x89PNG\r\n\x1a\n truncated garbage")

    screen.observer_edit.setText("AL")
    screen.stage_files([good_a, bad, good_b])
    warnings: list[str] = []
    monkeypatch.setattr(QMessageBox, "warning", lambda _p, _t, text, *a, **k: warnings.append(text))
    screen._import_staged()

    assert catalog.observation_count() == 2  # both readable files landed
    assert [name for name, _ in screen.last_import_errors] == ["truncated.png"]
    assert warnings and "truncated.png" in warnings[0]
    assert screen.staged_files() == []


def test_observations_saved_tick_updates_on_save(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    from PIL import Image as PilImage

    from herpetoid.api import ROI
    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.observations import ObservationsScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    image = tmp_path / "i.png"
    PilImage.fromarray(np.full((64, 64, 3), 120, np.uint8)).save(image)
    catalog.import_observation(species.id, [image])

    screen = ObservationsScreen(app_state)
    qtbot.addWidget(screen)
    assert screen.table.item(0, 3).text() == ""  # no ROI marked yet -> no tick (Saved column)
    screen.viewer.set_roi(ROI.rectangle(5, 5, 40, 40))
    screen.save()
    assert screen.table.item(0, 3).text() == "✓"  # tick appears in real time after saving the ROI


def test_observations_new_vs_recapture_columns(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    from PIL import Image as PilImage

    from herpetoid.api import ROI
    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.observations import ObservationsScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    paths = []
    for name in ("a.png", "b.png", "c.png"):
        p = tmp_path / name
        PilImage.fromarray(np.full((16, 16, 3), 120, np.uint8)).save(p)
        paths.append(p)
    first = catalog.import_observation(species.id, [paths[0]])
    second = catalog.import_observation(species.id, [paths[1]])  # same individual -> recapture
    catalog.import_observation(species.id, [paths[2]])  # left unidentified
    individual = catalog.create_individual(species.id, code="CA-001")
    for obs in (first, second):
        assert obs.id is not None
        catalog.link_observation(obs.id, individual.id)
        img = catalog.images_for(obs.id)[0]
        assert img.id is not None
        catalog.set_image_roi(img.id, ROI.rectangle(2, 2, 10, 10))
    # Only `first` is actually run through identification; `second` is merely linked to an individual.
    catalog.record_identification(first.id)

    screen = ObservationsScreen(app_state)
    qtbot.addWidget(screen)
    by_id = {int(screen.table.item(r, 0).text()): r for r in range(screen.table.rowCount())}
    # Identified column (4): tick only where identification was actually run (not for a mere link).
    assert screen.table.item(by_id[first.id], 4).text() == "✓"
    assert screen.table.item(by_id[second.id], 4).text() == ""
    # Type column (5): earliest linked observation is New, the later one is a Recapture.
    assert screen.table.item(by_id[first.id], 5).text() == "New"
    assert screen.table.item(by_id[second.id], 5).text() == "Recapture"


def test_individual_observation_navigation(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    from datetime import date

    from PIL import Image as PilImage

    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.individuals import IndividualBrowserScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    individual = catalog.create_individual(species.id, code="CA-001")
    for i, day in enumerate((10, 20)):
        p = tmp_path / f"obs{i}.png"
        PilImage.fromarray(np.full((16, 16, 3), 100 + i * 20, np.uint8)).save(p)
        obs = catalog.import_observation(
            species.id, [p], observed_at=date(2026, 5, day), observer=f"obs{i}"
        )
        assert obs.id is not None
        catalog.link_observation(obs.id, individual.id)

    screen = IndividualBrowserScreen(app_state)
    qtbot.addWidget(screen)
    screen.table.selectRow(0)
    # Two observations -> Next enabled, Prev disabled; position + date shown.
    assert "2 observation" in screen.individual_header.text()
    assert "Observation 1 of 2" in screen.obs_position_label.text()
    assert "10/05/2026" in screen.obs_position_label.text()  # dates read day-first everywhere
    assert not screen.prev_button.isEnabled()
    assert screen.next_button.isEnabled()

    screen._step_observation(1)  # arrow to the second observation
    assert "Observation 2 of 2" in screen.obs_position_label.text()
    assert "20/05/2026" in screen.obs_position_label.text()
    assert screen.prev_button.isEnabled()
    assert not screen.next_button.isEnabled()


def test_query_dropdowns_show_code_without_species(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    from PIL import Image as PilImage

    from herpetoid.api import ROI
    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.identification import IdentificationScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    image = tmp_path / "i.png"
    PilImage.fromarray(np.full((64, 64, 3), 120, np.uint8)).save(image)
    obs = catalog.import_observation(species.id, [image])
    assert obs.id is not None
    individual = catalog.create_individual(species.id, code="CA-001")
    catalog.link_observation(obs.id, individual.id)
    stored = catalog.images_for(obs.id)[0]
    assert stored.id is not None
    catalog.set_image_roi(stored.id, ROI.rectangle(5, 5, 40, 40))

    screen = IdentificationScreen(app_state)
    qtbot.addWidget(screen)
    assert screen.query_combo.itemText(0) == "CA-001"  # code only, no species in the label
    assert "Calotriton asper" in screen.query_species_label.text()
    assert screen.obs_a_combo.itemText(0) == "CA-001"
    screen.set_mode("compare")
    assert "Calotriton asper" in screen.species_label.text()


def test_dynamic_form_roundtrip_and_validation(qtbot) -> None:
    from herpetoid.gui.widgets.dynamic_form import DynamicForm
    from herpetoid.plugins.species.calotriton_asper import CalotritonAsperModule

    fields = CalotritonAsperModule().define_observation_fields()
    form = DynamicForm(fields)
    qtbot.addWidget(form)

    # Untouched numeric editors are empty (no misleading 0.000 default) and read back as None.
    fresh = form.values()
    assert fresh["svl"] is None
    assert fresh["weight"] is None

    form.set_values({"svl": 52.3, "sex": "female"})
    values = form.values()
    assert values["svl"] == 52.3
    assert values["weight"] is None  # still untouched
    assert values["sex"] == "female"
    assert form.validate().ok

    form.set_values({"svl": -5.0})  # below the field's min_value
    assert not form.validate().ok


def test_statistics_screen(app_state: AppState, tmp_path: Path, qtbot) -> None:
    from PIL import Image as PilImage

    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.statistics import StatisticsScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    image = tmp_path / "i.png"
    PilImage.fromarray(np.zeros((16, 16, 3), np.uint8)).save(image)
    catalog.import_observation(species.id, [image], measurements={"svl": 40.0, "sex": "female"})
    catalog.import_observation(species.id, [image], measurements={"svl": 50.0, "sex": "male"})

    screen = StatisticsScreen(app_state)
    qtbot.addWidget(screen)
    assert "Observations: 2" in screen.summary_label.text()
    # The table shows the species' declared display names (with units), not raw statistic keys.
    names = [screen.table.item(r, 0).text() for r in range(screen.table.rowCount())]
    assert "Mean SVL (mm)" in names
    assert "Sex ratio" in names
    assert "mean_svl" not in names
    # The per-format export buttons collapsed into one menu button.
    assert screen.export_button.menu() is not None
    assert [a.text() for a in screen.export_button.menu().actions()] == [
        "CSV",
        "Excel",
        "JSON",
        "PDF",
    ]


def test_settings_screen_changes_theme_and_style(app_state: AppState, qtbot) -> None:
    from herpetoid.gui.screens.settings import SettingsScreen

    screen = SettingsScreen(app_state)
    qtbot.addWidget(screen)
    screen.theme_combo.setCurrentIndex(screen.theme_combo.findData("dark"))
    assert app_state.settings.settings.theme == "dark"
    screen.style_combo.setCurrentIndex(screen.style_combo.findData("moss"))
    assert app_state.settings.settings.style == "moss"
    assert app_state.settings.settings.theme == "dark"  # changing style keeps the mode
    screen.top_k_spin.setValue(7)
    assert app_state.settings.settings.default_top_k == 7
    # Every offered style has a swatch icon and resolvable id.
    assert screen.style_combo.count() >= 2
    for index in range(screen.style_combo.count()):
        assert not screen.style_combo.itemIcon(index).isNull()


def test_theme_stylesheet_covers_shell_chrome_for_all_styles(qtbot) -> None:
    from PySide6.QtWidgets import QApplication

    from herpetoid.gui.theme import ThemeManager, _stylesheet, available_styles, get_style

    styles = available_styles()
    assert {"teal", "moss", "slate", "clay"} <= {s.style_id for s in styles}
    for style in styles:
        for mode in ("light", "dark"):
            sheet = _stylesheet(style, mode)
            for selector in (
                "QMenuBar",
                "QMenu",
                "QToolBar",
                "QTabBar::tab",
                "QDockWidget",
                "QLabel#sectionTitle",
                "QLabel#toast",
                "QFrame#homeCard",
                "QStatusBar::item",
            ):
                assert selector in sheet
            assert style.accent in sheet

    # Unknown/legacy style ids fall back to the default instead of crashing.
    assert get_style("does-not-exist").style_id == "teal"
    assert get_style(None).style_id == "teal"

    # Every style applies cleanly in both modes on a real QApplication.
    app = QApplication.instance()
    assert app is not None
    manager = ThemeManager(app)
    for style in styles:
        assert manager.apply("dark", style.style_id) == "dark"
        assert manager.apply("light", style.style_id) == "light"
    manager.apply("light", "teal")  # leave the shared QApplication in the default look


def test_icons_render_for_all_glyphs(qtbot) -> None:
    from herpetoid.gui.icons import icon, icon_names

    names = icon_names()
    assert {"new-project", "import", "identify", "export", "settings", "help"} <= set(names)
    for name in names:
        rendered = icon(name)
        assert not rendered.isNull()
        assert not rendered.pixmap(20, 20).isNull()


def test_observations_screen_lists_and_shows_image(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    from PIL import Image as PilImage

    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.observations import ObservationsScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    image = tmp_path / "i.png"
    PilImage.fromarray(np.full((16, 16, 3), 120, np.uint8)).save(image)
    catalog.import_observation(species.id, [image], observer="AL", measurements={"svl": 40.0})

    screen = ObservationsScreen(app_state)
    qtbot.addWidget(screen)
    assert screen.table.rowCount() == 1
    assert screen.table.item(0, 1).text() == "AL"  # observer column
    assert screen.viewer.has_image()  # first row auto-selected, image shown without a click
    screen.table.selectRow(0)
    assert screen.viewer.has_image()


def test_roi_image_viewer_roundtrip(qtbot) -> None:
    from herpetoid.api import ROI, ROIKind
    from herpetoid.gui.widgets.roi_image_viewer import RoiImageViewer

    viewer = RoiImageViewer()
    qtbot.addWidget(viewer)
    viewer.set_image(np.zeros((64, 64, 3), np.uint8))
    assert viewer.roi() is None
    viewer.set_roi(ROI.rectangle(4, 5, 20, 15))
    marked = viewer.roi()
    assert marked is not None
    assert marked.kind is ROIKind.RECTANGLE
    assert marked.bounding_box() == (4, 5, 20, 15)
    viewer.set_draw_mode(True)  # switches interaction mode without error
    viewer.clear_roi()
    assert viewer.roi() is None


def test_roi_image_viewer_polygon_roundtrip(qtbot) -> None:
    from herpetoid.api import ROI, ROIKind
    from herpetoid.gui.widgets.roi_image_viewer import RoiImageViewer

    viewer = RoiImageViewer()
    qtbot.addWidget(viewer)
    viewer.set_image(np.zeros((64, 64, 3), np.uint8))
    viewer.set_roi_kind(ROIKind.POLYGON)

    polygon = ROI(kind=ROIKind.POLYGON, points=((5, 5), (40, 8), (30, 45), (8, 38)))
    viewer.set_roi(polygon)
    marked = viewer.roi()
    assert marked is not None
    assert marked.kind is ROIKind.POLYGON
    assert len(marked.points) == 4
    assert marked.bounding_box() == (5, 5, 35, 40)

    # the preview reflects the marked (masked) region, cropped to the polygon's bounding box
    preview = viewer.roi_preview()
    assert preview is not None
    assert preview.shape == (40, 35, 3)

    viewer.undo_point()  # 3 points left -> still a valid polygon
    assert viewer.roi() is not None
    viewer.undo_point()  # 2 points left -> not enough for a polygon
    assert viewer.roi() is None


def test_observation_editor_saves_measurements_and_roi(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    from PIL import Image as PilImage

    from herpetoid.api import ROI
    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.observations import ObservationsScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    image_path = tmp_path / "i.png"
    PilImage.fromarray(np.full((64, 64, 3), 120, np.uint8)).save(image_path)
    observation = catalog.import_observation(species.id, [image_path], observer="AL")
    assert observation.id is not None

    screen = ObservationsScreen(app_state)
    qtbot.addWidget(screen)
    # first row auto-selected -> editor loaded with a species measurement form
    assert screen._current is not None
    assert screen._form is not None

    screen.observer_edit.setText("BM")
    screen.notes_edit.setText("ventral photo")
    screen.lat_edit.setText("42.6")
    screen._form.set_values({"svl": 51.0, "sex": "female"})
    screen.viewer.set_roi(ROI.rectangle(5, 6, 30, 20))
    screen.save()

    reloaded = catalog.get_observation(observation.id)
    assert reloaded is not None
    assert reloaded.observer == "BM"
    assert reloaded.notes == "ventral photo"
    assert reloaded.location.latitude == 42.6
    assert reloaded.measurements["svl"] == 51.0
    assert reloaded.measurements["sex"] == "female"

    stored_image = catalog.images_for(observation.id)[0]
    assert stored_image.id is not None
    saved_roi = catalog.get_image_roi(stored_image.id)
    assert saved_roi is not None
    assert saved_roi.bounding_box() == (5, 6, 30, 20)


def test_reopen_last_project_on_launch(app_state: AppState, tmp_path: Path) -> None:
    from herpetoid.gui.app import reopen_last_project

    app_state.settings.add_recent_project(str(tmp_path / "does-not-exist"))  # stale entry, skipped
    app_state.create_project(tmp_path / "proj", "Kept")
    app_state.close_project()
    assert app_state.project is None

    reopen_last_project(app_state)  # picks up the most recent still-existing bundle
    assert app_state.project is not None
    assert app_state.project.project.name == "Kept"


def test_home_screen_actions_and_status(app_state: AppState, tmp_path: Path, qtbot) -> None:
    from PySide6.QtWidgets import QLabel

    from herpetoid.gui.screens.home import HomeScreen, _ActionCard

    visited: list[str] = []
    screen = HomeScreen(app_state, visited.append)
    qtbot.addWidget(screen)

    cards = screen.findChildren(_ActionCard)
    assert len(cards) == 8
    cards[0]._on_click()  # the first quick-action card navigates
    assert visited == ["Projects"]

    # No project yet -> the status card prompts to open one.
    assert any("No project open" in w.text() for w in screen.findChildren(QLabel))

    # Opening a project refreshes the status card with the project name + live stats.
    app_state.create_project(tmp_path / "proj", "MyStudy")
    texts = [w.text() for w in screen.findChildren(QLabel)]
    assert any("MyStudy" in t for t in texts)


def test_nav_order_workflow(app_state: AppState, qtbot) -> None:
    window = MainWindow(app_state)
    qtbot.addWidget(window)
    names = window.screen_names()
    assert names.index("Observations") < names.index("Individuals")
    assert names.index("Individuals") < names.index("Identification")
    assert names.index("Identification") < names.index("Statistics")


def test_new_code_stays_pending_until_confirmed_in_identification(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    """Saving a new code must NOT create the individual — only Identification confirms it."""
    from PIL import Image as PilImage

    from herpetoid.api import ROI
    from herpetoid.application.catalog_service import pending_code
    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.identification import IdentificationScreen
    from herpetoid.gui.screens.observations import ObservationsScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    image = tmp_path / "i.png"
    PilImage.fromarray(np.full((64, 64, 3), 120, np.uint8)).save(image)
    obs = catalog.import_observation(species.id, [image])
    assert obs.id is not None

    editor = ObservationsScreen(app_state)
    qtbot.addWidget(editor)
    assert editor._current is not None  # first row auto-selected
    editor.code_edit.setText("CA-777")
    editor.viewer.set_roi(ROI.rectangle(5, 5, 40, 40))
    editor.save()

    # No individual yet: the code is pending, visible in the table with a "?" marker.
    assert catalog.find_individual_by_code(species.id, "CA-777") is None
    assert catalog.individual_count() == 0
    reloaded = catalog.get_observation(obs.id)
    assert reloaded is not None and reloaded.individual_id is None
    assert pending_code(reloaded) == "CA-777"
    assert "pending" in editor.status_label.text()
    assert editor.table.item(0, 2).text() == "CA-777 ?"
    assert editor.code_edit.text() == "CA-777"  # reloading the editor keeps the typed code

    # The query picker labels it as pending; confirming via "Mark as new" creates it with that code.
    screen = IdentificationScreen(app_state)
    qtbot.addWidget(screen)
    assert screen.query_combo.count() == 1
    assert screen.query_combo.itemData(0) == obs.id
    assert "CA-777 (pending)" in screen.query_combo.itemText(0)
    screen._query_observation_id = obs.id
    screen.mark_new()
    individual = catalog.find_individual_by_code(species.id, "CA-777")
    assert individual is not None
    linked = catalog.get_observation(obs.id)
    assert linked is not None and linked.individual_id == individual.id
    assert pending_code(linked) is None  # pending marker consumed

    # Marking again must NOT mint a duplicate individual — but it must still read as a decision
    # taken, not as a dead button: the verdict "not a recapture" keeps the identity it has.
    screen._query_observation_id = obs.id
    screen.mark_new()
    assert catalog.individual_count() == 1
    assert "Kept as individual CA-777" in screen.status_label.text()
    assert "CA-777" in screen.toast.text()  # and it is toasted, not just written to a corner

    # A code that matches an existing individual still links directly on save.
    other = catalog.import_observation(species.id, [image])
    assert other.id is not None
    app_state.project_changed.emit()  # refresh the editor's list with the new observation
    editor.select_observation(other.id)
    editor.code_edit.setText("CA-777")
    editor.save()
    relinked = catalog.get_observation(other.id)
    assert relinked is not None and relinked.individual_id == individual.id
    assert catalog.individual_count() == 1






def _spot_pattern(seed: int, size: int = 256, count: int = 45) -> np.ndarray:
    import cv2

    rng = np.random.default_rng(seed)
    img = np.full((size, size), 255, np.uint8)
    for _ in range(count):
        cx, cy = rng.integers(20, size - 20, size=2)
        ax, ay = rng.integers(5, 15, size=2)
        cv2.ellipse(
            img, (int(cx), int(cy)), (int(ax), int(ay)), int(rng.integers(0, 180)), 0, 360, 0, -1
        )
    return img


def _save_gray(path: Path, gray: np.ndarray) -> None:
    from PIL import Image as PilImage

    PilImage.fromarray(np.stack([gray, gray, gray], axis=-1)).save(path)


def _identification_project(app_state: AppState, tmp_path: Path):
    """A project with three enrolled spot patterns (a, b=rotated a, c) and un-enrolled d."""
    import cv2

    from herpetoid.api import ROI
    from herpetoid.domain import PluginRef

    def rotate(img: np.ndarray, deg: float) -> np.ndarray:
        h, w = img.shape[:2]
        return cv2.warpAffine(
            img, cv2.getRotationMatrix2D((w / 2, h / 2), deg, 1.0), (w, h), borderValue=255
        )

    cv2.setRNGSeed(7)
    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    base = _spot_pattern(1)
    pa, pb, pc, pd = (tmp_path / f"{n}.png" for n in "abcd")
    _save_gray(pa, base)
    _save_gray(pb, rotate(base, 10))
    _save_gray(pc, _spot_pattern(999))
    _save_gray(pd, _spot_pattern(500))
    obs_a = catalog.import_observation(
        species.id, [pa], measurements={"svl": 50.0, "sex": "female"}
    )
    obs_b = catalog.import_observation(species.id, [pb])
    obs_c = catalog.import_observation(species.id, [pc])
    obs_d = catalog.import_observation(species.id, [pd])  # not enrolled -> must be excluded

    individuals = {}
    for obs in (obs_a, obs_b, obs_c):
        assert obs.id is not None
        individual = catalog.create_individual(species.id)
        catalog.link_observation(obs.id, individual.id)
        image = catalog.images_for(obs.id)[0]
        assert image.id is not None
        catalog.set_image_roi(image.id, ROI.rectangle(10, 10, 236, 236))
        individuals[obs.id] = individual
    return catalog, obs_a, obs_b, obs_c, obs_d, individuals


def test_identification_screen_identify_select_confirm(
    app_state: AppState, tmp_path: Path, qtbot, monkeypatch
) -> None:
    from herpetoid.application.identification_runner import IdentificationRunner
    from herpetoid.gui.screens.identification import IdentificationScreen

    catalog, obs_a, obs_b, _obs_c, obs_d, individuals = _identification_project(
        app_state, tmp_path
    )

    compare_calls: list[tuple[int, int]] = []
    original_compare = IdentificationRunner.compare

    def counting_compare(self, a_id: int, b_id: int, algorithm_id: str):
        compare_calls.append((a_id, b_id))
        return original_compare(self, a_id, b_id, algorithm_id)

    monkeypatch.setattr(IdentificationRunner, "compare", counting_compare)

    screen = IdentificationScreen(app_state)
    qtbot.addWidget(screen)
    assert screen.query_combo.count() == 3  # a, b, c — not the un-enrolled d
    assert screen.query_combo.findData(obs_d.id) == -1
    screen.query_combo.setCurrentIndex(screen.query_combo.findData(obs_a.id))
    screen.algorithm_combo.setCurrentIndex(screen.algorithm_combo.findData("orb"))

    assert catalog.identified_observation_ids() == set()
    screen.identify()

    assert screen._candidates
    assert screen._candidates[0].observation.id == obs_b.id  # same individual (rotated) first
    assert obs_a.id in catalog.identified_observation_ids()  # a real run was recorded
    assert screen.query_panel.viewer.has_image()
    assert screen.query_panel.info.rowCount() > 0  # species-driven info panel (svl, sex, …)
    assert not screen.query_panel.roi.pixmap().isNull()

    # The first card is auto-selected: match evidence was computed lazily exactly once and shown.
    assert screen.cards.currentRow() == 0
    assert len(compare_calls) == 1
    assert screen.overlay.viewer.has_image()
    assert screen.overlay._comparison is not None
    assert screen.candidate_info.rowCount() > 0
    card = screen.cards.itemWidget(screen.cards.item(0))
    assert "inliers" in card.detail_label.text()  # detail line back-filled from the comparison
    # The inlier ratio is not evidence (ORB 1.1): showing it only invites misreading a match.
    assert "ratio" not in card.detail_label.text()
    assert "ratio" not in screen.overlay.detail_label.text()

    # Re-selecting an already-computed card hits the cache (no extra compare run).
    screen.select_candidate(1)
    assert len(compare_calls) == 2
    screen.select_candidate(0)
    assert len(compare_calls) == 2

    screen.confirm_same()  # links the query to the selected candidate's individual
    reloaded_a = catalog.get_observation(obs_a.id)
    assert reloaded_a is not None
    assert reloaded_a.individual_id == individuals[obs_b.id].id  # now share one individual


def test_identification_screen_show_more(app_state: AppState, tmp_path: Path, qtbot) -> None:
    from herpetoid.gui.screens.identification import IdentificationScreen

    _catalog, obs_a, _obs_b, _obs_c, _obs_d, _individuals = _identification_project(
        app_state, tmp_path
    )
    app_state.settings.settings.default_top_k = 1

    screen = IdentificationScreen(app_state)
    qtbot.addWidget(screen)
    screen.query_combo.setCurrentIndex(screen.query_combo.findData(obs_a.id))
    screen.algorithm_combo.setCurrentIndex(screen.algorithm_combo.findData("orb"))
    screen.identify()

    assert len(screen._candidates) == 1
    assert screen.cards.count() == 1
    assert screen.show_more_button.isEnabled()  # the run filled top-k, so more may exist
    screen.show_more()
    assert len(screen._candidates) == 2  # b and c against query a
    assert screen.cards.count() == 2
    assert screen.show_more_button.isEnabled()  # 2 filled the requested 2 — more may exist
    screen.show_more()
    assert len(screen._candidates) == 2
    assert not screen.show_more_button.isEnabled()  # 2 < the requested 3: catalog exhausted


def test_identification_screen_unassigned_query_selectable(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    from PIL import Image as PilImage

    from herpetoid.api import ROI
    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.identification import IdentificationScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    image = tmp_path / "i.png"
    PilImage.fromarray(np.full((64, 64, 3), 120, np.uint8)).save(image)
    obs = catalog.import_observation(species.id, [image])
    assert obs.id is not None
    stored = catalog.images_for(obs.id)[0]
    assert stored.id is not None
    catalog.set_image_roi(stored.id, ROI.rectangle(5, 5, 40, 40))  # ROI only, no individual

    screen = IdentificationScreen(app_state)
    qtbot.addWidget(screen)
    # It must still be selectable as a query so it *can* be identified/assigned.
    assert screen.query_combo.count() == 1
    assert screen.query_combo.itemData(0) == obs.id
    assert "unassigned" in screen.query_combo.itemText(0)
    assert "Calotriton asper" in screen.query_species_label.text()


def test_identification_first_individual_dialog_and_code_prompt(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    """Identifying against an empty catalog offers to enrol the query as the FIRST individual.

    Cancel backs out without creating anything; accepting with no code typed prompts for one
    (prefilled with the default), and the typed code is used for the created individual.
    """
    from PySide6.QtWidgets import QMessageBox

    from herpetoid.api import ROI
    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.identification import IdentificationScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    image = tmp_path / "a.png"
    _save_gray(image, _spot_pattern(3))
    obs = catalog.import_observation(species.id, [image])  # no individual code typed anywhere
    assert obs.id is not None
    stored = catalog.images_for(obs.id)[0]
    assert stored.id is not None
    catalog.set_image_roi(stored.id, ROI.rectangle(10, 10, 236, 236))

    screen = IdentificationScreen(app_state)
    qtbot.addWidget(screen)
    screen.query_combo.setCurrentIndex(screen.query_combo.findData(obs.id))
    screen.algorithm_combo.setCurrentIndex(screen.algorithm_combo.findData("orb"))
    screen.identify()
    assert not screen._candidates
    dialog = screen._first_dialog
    assert dialog is not None and dialog.isVisible()
    assert "first individual" in screen.status_label.text()

    # Cancel goes back without creating anything.
    cancel = dialog.button(QMessageBox.StandardButton.Cancel)
    assert cancel is not None
    cancel.click()
    assert catalog.individual_count() == 0

    # Run again and accept: no code was typed, so a prompt appears prefilled with the default.
    screen.identify()
    assert screen._first_mark_button is not None
    screen._first_mark_button.click()
    code_dialog = screen._first_code_dialog
    assert code_dialog is not None and code_dialog.isVisible()
    assert code_dialog.code_edit.text() == "IND-001"
    code_dialog.code_edit.setText("FIRST-01")
    code_dialog.accept()
    individual = catalog.find_individual_by_code(species.id, "FIRST-01")
    assert individual is not None
    linked = catalog.get_observation(obs.id)
    assert linked is not None and linked.individual_id == individual.id
    assert "first individual" in screen.status_label.text()


def test_identification_screen_compare_mode(app_state: AppState, tmp_path: Path, qtbot) -> None:
    from herpetoid.gui.screens.identification import IdentificationScreen

    _catalog, obs_a, obs_b, _obs_c, _obs_d, _individuals = _identification_project(
        app_state, tmp_path
    )

    screen = IdentificationScreen(app_state)
    qtbot.addWidget(screen)
    assert screen.mode() == "identify"
    screen.set_mode("compare")
    assert screen.mode() == "compare"
    assert screen._matches_panel.isHidden()  # the ranked cards only apply to identify mode

    screen.obs_a_combo.setCurrentIndex(screen.obs_a_combo.findData(obs_a.id))
    screen.obs_b_combo.setCurrentIndex(screen.obs_b_combo.findData(obs_b.id))
    screen.algorithm_combo.setCurrentIndex(screen.algorithm_combo.findData("orb"))
    screen.compare()

    assert screen._comparison is not None
    assert screen._comparison.result.inliers > 0  # rotated copy still produces inlier matches
    assert screen.overlay.viewer.has_image()  # the side-by-side composite is shown
    assert screen.query_panel.viewer.has_image()  # A is shown in the left panel

    screen.set_mode("identify")
    assert not screen._matches_panel.isHidden()


def test_build_match_composite_dimensions() -> None:
    from herpetoid.gui.widgets.match_overlay import build_match_composite

    left = np.zeros((40, 30), np.uint8)
    right = np.zeros((50, 20), np.uint8)
    corr = np.array([[5, 5, 4, 4], [10, 20, 8, 18]], float)
    composite = build_match_composite(left, right, corr)
    assert composite.shape[0] == 50  # both patterns normalized to the tallest height
    assert composite.shape[2] == 3  # RGB
    # The left pattern is scaled 50/40 = 1.25x to match: width 30 -> 38. Both then get a panel of
    # that same width, so the pair reads as two equal spaces however narrow one pattern is.
    assert composite.shape[1] == 38 + 24 + 38  # panel + gap + panel


def test_build_match_composite_normalizes_orientation_and_size() -> None:
    """Landscape patterns are rotated upright and both sides share one height (like-for-like pair)."""
    from herpetoid.gui.widgets.match_overlay import build_match_composite

    landscape = np.zeros((30, 40), np.uint8)  # wider than tall -> must be rotated to 40x30
    portrait = np.zeros((50, 20), np.uint8)
    corr = np.array([[39, 0, 4, 4]], float)  # top-right corner of the landscape query
    composite = build_match_composite(landscape, portrait, corr)
    assert composite.shape[0] == 50  # rotated left (40 tall) scaled up to the right's 50
    panel = round(30 * 50 / 40)  # 38 after the 1.25x scale; the wider of the two sets the panel
    assert composite.shape[1] == panel + 24 + panel
    # The overlay must still land on the canvas: something was drawn (composite differs from plain).
    plain = build_match_composite(landscape, portrait, corr, show_lines=False, show_points=False)
    assert not np.array_equal(plain, composite)
    # The left pattern fills its panel; the narrower right one is centred in its own, so the
    # background shows either side of it rather than the pair being butted together.
    assert not (plain[:, :panel] == 245).all(axis=2).any()  # left panel fully covered
    right_pad = (panel - 20) // 2
    right0 = panel + 24 + right_pad
    assert not (plain[:, right0 : right0 + 20] == 245).all(axis=2).any()  # the pattern itself
    assert (plain[:, panel + 24 : right0] == 245).all()  # padding, in the given background


def test_build_match_composite_paints_the_surrounding_interface_colours() -> None:
    """The panels sit on the application's own surface, not on a hard-coded slab."""
    from herpetoid.gui.widgets.match_overlay import build_match_composite

    left = np.zeros((40, 30), np.uint8)
    right = np.zeros((40, 20), np.uint8)
    dark = (23, 25, 28)  # the dark theme's base
    composite = build_match_composite(left, right, None, background=dark, frame=(154, 160, 166))

    gap = composite[:, 30 : 30 + 24]  # between the two panels
    assert (gap[2:-2] == dark).all()  # ...the background, except where the frames are drawn
    # Each panel is outlined, so its corner is the frame colour rather than the background.
    assert tuple(composite[0, 0]) != dark
    assert tuple(composite[0, 30 + 24]) != dark


def test_build_match_composite_overlay_options() -> None:
    from herpetoid.gui.widgets.match_overlay import build_match_composite

    left = np.full((60, 50, 3), 200, np.uint8)
    right = np.full((60, 50, 3), 200, np.uint8)
    corr = np.array([[5, 5, 6, 6], [10, 10, 11, 11], [20, 20, 21, 21]], float)

    plain = build_match_composite(left, right, corr, show_lines=False, show_points=False)
    drawn = build_match_composite(left, right, corr)
    # with an overlay the image differs from the plain side-by-side
    assert not np.array_equal(plain, drawn)
    # hiding everything, zero opacity, and zero matches all fall back to the plain composite
    assert np.array_equal(plain, build_match_composite(left, right, corr, opacity=0.0))
    assert np.array_equal(plain, build_match_composite(left, right, corr, max_matches=0))
    # limiting the count draws less than showing all
    one = build_match_composite(left, right, corr, max_matches=1)
    assert (one != plain).sum() < (drawn != plain).sum()


def test_individual_browser(app_state: AppState, tmp_path: Path, qtbot) -> None:
    from PIL import Image as PilImage

    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.individuals import IndividualBrowserScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    image = tmp_path / "i.png"
    PilImage.fromarray(np.full((16, 16, 3), 100, np.uint8)).save(image)
    observation = catalog.import_observation(
        species.id, [image], observer="AL", measurements={"svl": 40.0}
    )
    individual = catalog.create_individual(species.id, code="CA-001")
    assert observation.id is not None
    catalog.link_observation(observation.id, individual.id)

    screen = IndividualBrowserScreen(app_state)
    qtbot.addWidget(screen)
    assert screen.table.rowCount() == 1
    assert screen.table.item(0, 0).text() == "CA-001"
    assert screen.table.item(0, 4).text() == "1"  # one linked observation (Obs. column)
    assert "CA-001" in screen.individual_header.text()  # individual header shows the code
    assert screen.viewer.has_image()
    assert screen.info_table.rowCount() > 0  # the observation's details panel is populated


def test_individual_editor_updates_code_and_measurements(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    from PIL import Image as PilImage

    from herpetoid.domain import PluginRef, Sex
    from herpetoid.gui.screens.individuals import IndividualBrowserScreen, IndividualEditDialog

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    image = tmp_path / "i.png"
    PilImage.fromarray(np.full((16, 16, 3), 100, np.uint8)).save(image)
    observation = catalog.import_observation(species.id, [image])
    individual = catalog.create_individual(species.id, code="CA-001")
    assert observation.id is not None
    catalog.link_observation(observation.id, individual.id)

    screen = IndividualBrowserScreen(app_state)
    qtbot.addWidget(screen)

    fields = list(app_state.registry.create_module("calotriton_asper").define_observation_fields())
    dialog = IndividualEditDialog(individual, fields, {}, screen)
    dialog.code_edit.setText("CA-042")
    dialog.sex_combo.setCurrentText("female")
    dialog._form.set_values({"svl": 48.5})  # measurement written to the individual's observation
    catalog.update_individual(dialog.updated_individual())
    representative = catalog.observations_for_individual(individual.id)[0]
    representative.measurements = dialog.measurement_values()
    catalog.update_observation(representative)

    reloaded = catalog.get_individual(individual.id)
    assert reloaded is not None
    assert reloaded.code == "CA-042"
    assert reloaded.sex is Sex.FEMALE
    reloaded_obs = catalog.observations_for_individual(individual.id)[0]
    assert reloaded_obs.measurements["svl"] == 48.5


def test_clearing_a_roi_removes_it_for_good(app_state: AppState, tmp_path: Path, qtbot) -> None:
    """Regression: clearing a region only wiped the screen.

    Reported together: on a saved (read-only) observation the region vanished from the view while
    "Draw polygon" was disabled, leaving no way to put it back — and saving never wrote the *absence*
    of a region, so the old polygon stayed in the database and reappeared on re-selection.

    The ROI tools are therefore never disabled on a loaded observation: reaching for one *is* the
    intent to edit, so it unlocks the observation itself rather than sitting there doing nothing.
    """
    from PIL import Image as PilImage

    from herpetoid.api import ROI
    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.observations import ObservationsScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    for name in ("a.png", "b.png"):
        path = tmp_path / name
        PilImage.fromarray(np.full((64, 64, 3), 120, np.uint8)).save(path)
        catalog.import_observation(species.id, [path])

    screen = ObservationsScreen(app_state)
    qtbot.addWidget(screen)
    first, second = (obs.id for obs in catalog.list_observations())
    assert first is not None and second is not None
    image_id = catalog.images_for(first)[0].id
    assert image_id is not None

    # Mark a region and save it, as the user would.
    screen.select_observation(first)
    screen.viewer.set_roi(ROI.rectangle(5, 5, 40, 40))
    screen.save()
    assert catalog.get_image_roi(image_id) is not None
    by_id = {int(screen.table.item(r, 0).text()): r for r in range(screen.table.rowCount())}
    assert screen.table.item(by_id[first], 3).text() == "✓"  # the "Saved" tick

    # Re-opened locked: the text fields are read-only behind "Edit", but the ROI tools stay live.
    assert screen.save_button.text() == "Edit"
    assert not screen.observer_edit.isEnabled()
    assert screen.draw_button.isEnabled()
    assert screen.clear_roi_button.isEnabled()

    # Clearing works straight away and takes the observation into edit mode with it.
    screen.clear_roi_button.click()
    assert screen.viewer.roi() is None
    assert not screen._locked
    assert screen.save_button.text() == "Save changes"
    assert screen.observer_edit.isEnabled()
    assert screen.draw_button.isEnabled()  # still able to draw a replacement
    assert "cleared" in screen.status_label.text()
    screen.save()

    # Gone from the database, gone from the table, and gone after navigating away and back.
    assert catalog.get_image_roi(image_id) is None
    assert not catalog.has_roi(first)
    by_id = {int(screen.table.item(r, 0).text()): r for r in range(screen.table.rowCount())}
    assert screen.table.item(by_id[first], 3).text() == ""
    screen.select_observation(second)
    screen.select_observation(first)
    assert screen.viewer.roi() is None, "the cleared region came back"

    # Drawing on a saved observation unlocks it the same way, so a region can be replaced directly.
    screen.viewer.set_roi(ROI.rectangle(8, 8, 30, 30))
    screen.save()
    assert screen.save_button.text() == "Edit"  # saved -> locked again
    screen.draw_button.setChecked(True)
    assert not screen._locked and screen.save_button.text() == "Save changes"
    screen.draw_button.setChecked(False)


def test_help_screen_renders_manual(qtbot) -> None:
    from herpetoid.gui.screens.help import HelpScreen

    screen = HelpScreen()
    qtbot.addWidget(screen)
    assert screen.toc.count() >= 5
    assert "HerpetoID" in screen.browser.toPlainText()  # first chapter rendered


def test_statistics_screen_exports(app_state: AppState, tmp_path: Path, qtbot) -> None:
    from PIL import Image as PilImage

    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.statistics import StatisticsScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    image = tmp_path / "i.png"
    PilImage.fromarray(np.full((16, 16, 3), 80, np.uint8)).save(image)
    catalog.import_observation(species.id, [image], observer="AL", measurements={"svl": 40.0})

    screen = StatisticsScreen(app_state)
    qtbot.addWidget(screen)

    csv_dest = tmp_path / "out.csv"
    screen.export_to("csv", csv_dest)
    assert csv_dest.exists()
    assert "observation_id" in csv_dest.read_text(encoding="utf-8")

    pdf_dest = tmp_path / "out.pdf"
    screen.export_to("pdf", pdf_dest)
    assert pdf_dest.read_bytes()[:4] == b"%PDF"


def _import_as(app_state: AppState, tmp_path: Path, species: str, names: list[str], qtbot) -> None:
    """Import images under a chosen species, through the real import screen."""
    from PIL import Image as PilImage

    from herpetoid.gui.screens.import_images import ImageImportScreen

    screen = ImageImportScreen(app_state)
    qtbot.addWidget(screen)
    screen.species_combo.setCurrentText(species)
    screen.observer_edit.setText("AL")
    paths = []
    for name in names:
        path = tmp_path / name
        PilImage.fromarray(np.zeros((16, 16, 3), np.uint8)).save(path)
        paths.append(path)
    assert screen.import_files(paths) == len(names)


def test_change_species_moves_a_whole_project_and_drops_the_empty_species(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    """The reported problem: a session imported under the wrong species, with no way to change it."""
    app_state.create_project(tmp_path / "proj", "P")
    _import_as(app_state, tmp_path, "Calotriton asper", ["a.png", "b.png", "c.png"], qtbot)
    catalog = app_state.catalog
    assert catalog is not None

    window = MainWindow(app_state)
    qtbot.addWidget(window)
    assert "Calotriton asper" in window._species_status.text()  # what the researcher sees, and reports

    dialog = window.open_change_species_dialog()
    qtbot.addWidget(dialog)
    assert "Calotriton asper" in dialog.from_combo.currentText()
    assert "3 observation(s)" in dialog.from_combo.currentText()
    dialog.to_combo.setCurrentText("Salamandra salamandra")
    assert dialog.observation_ids() == [o.id for o in catalog.list_observations()]
    assert "3 observation(s)" in dialog.consequences.text()

    report = dialog.apply_change()
    assert report is not None and report.observations == 3
    assert [s.scientific_name for s in catalog.list_species()] == ["Salamandra salamandra"]
    assert report.species_removed == ("Calotriton asper",)
    assert "Salamandra salamandra" in window._species_status.text()  # and the project stops lying


def test_change_species_from_the_observations_screen_moves_only_that_capture(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    from herpetoid.gui.screens.observations import ObservationsScreen

    app_state.create_project(tmp_path / "proj", "P")
    _import_as(app_state, tmp_path, "Calotriton asper", ["a.png", "b.png"], qtbot)
    catalog = app_state.catalog
    assert catalog is not None

    editor = ObservationsScreen(app_state)
    qtbot.addWidget(editor)
    first, second = sorted(o.id for o in catalog.list_observations())
    editor.select_observation(first)
    assert editor.species_label.text() == "Calotriton asper"  # visible where the mistake is visible

    dialog = editor.open_change_species()
    qtbot.addWidget(dialog)
    # Opened from a row, so the narrower scope is offered and preselected.
    assert dialog.scope_combo.currentData() == "one"
    assert dialog.observation_ids() == [first]
    dialog.to_combo.setCurrentText("Salamandra salamandra")
    report = dialog.apply_change()

    assert report is not None and report.observations == 1
    by_id = {o.id: o for o in catalog.list_observations()}
    species = {s.id: s.scientific_name for s in catalog.list_species()}
    assert species[by_id[first].species_id] == "Salamandra salamandra"
    assert species[by_id[second].species_id] == "Calotriton asper"  # untouched
    editor.select_observation(first)
    assert editor.species_label.text() == "Salamandra salamandra"


def test_change_species_warns_about_values_the_destination_does_not_use(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    """Moving to a species with fewer fields must say so — the values are kept, just not shown."""
    app_state.create_project(tmp_path / "proj", "P")
    _import_as(app_state, tmp_path, "Salamandra salamandra", ["a.png"], qtbot)
    catalog = app_state.catalog
    assert catalog is not None
    observation = catalog.list_observations()[0]
    assert observation.id is not None
    observation.measurements = {"svl": 90.0, "total_length": 180.0, "pattern_type": "spotted"}
    catalog.update_observation(observation)

    window = MainWindow(app_state)
    qtbot.addWidget(window)
    dialog = window.open_change_species_dialog()
    qtbot.addWidget(dialog)
    dialog.to_combo.setCurrentText("Calotriton asper")
    text = dialog.consequences.text()
    assert "Total length" in text and "Dorsal pattern" in text  # by label, not by key
    assert "SVL" not in text  # a field both species declare carries over untouched

    assert dialog.apply_change() is not None
    # Kept, not deleted: changing back restores them.
    moved = catalog.list_observations()[0]
    assert moved.measurements["total_length"] == 180.0
    assert moved.measurements["pattern_type"] == "spotted"


def test_import_will_not_file_captures_under_a_species_nobody_chose(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    """The root cause: the combo used to open on a species the researcher never picked."""
    from PIL import Image as PilImage

    from herpetoid.gui.screens.import_images import ImageImportScreen

    app_state.create_project(tmp_path / "proj", "P")
    screen = ImageImportScreen(app_state)
    qtbot.addWidget(screen)
    catalog = app_state.catalog
    assert catalog is not None

    assert screen.selected_species() is None  # a placeholder, not the first installed module
    source = tmp_path / "a.png"
    PilImage.fromarray(np.zeros((16, 16, 3), np.uint8)).save(source)
    screen.observer_edit.setText("AL")
    screen.stage_files([source])
    assert not screen.import_button.isEnabled()
    assert "a species" in screen.add_hint.text()
    assert screen.import_files([source]) == 0  # and nothing gets in by another route
    assert catalog.observation_count() == 0

    screen.species_combo.setCurrentText("Salamandra salamandra")
    assert screen.import_button.isEnabled()
    assert screen.import_files([source]) == 1

    # Once the project holds exactly one species it has declared itself: the next import screen
    # opens on it, so repeat imports stay one click.
    again = ImageImportScreen(app_state)
    qtbot.addWidget(again)
    assert again.selected_species() == "Salamandra salamandra"


def test_not_a_recapture_keeps_the_identity_of_an_already_cataloged_query(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    """Re-assessing cataloged captures (e.g. after a species change) must not be a dead button.

    The query already *is* an individual, so there is nothing new to mint — but the verdict "not a
    recapture of any candidate" is still a real decision, and it has to visibly land.
    """
    from herpetoid.api import ROI
    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.identification import IdentificationScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None

    # Three captures, each already a cataloged individual with a ROI — as after an identified season.
    ids = []
    for index in range(3):
        source = tmp_path / f"{index}.png"
        _write_image(source)
        observation = catalog.import_observation(species.id, [source], observer="AL")
        assert observation.id is not None
        image = catalog.images_for(observation.id)[0]
        assert image.id is not None
        catalog.set_image_roi(image.id, ROI.rectangle(2, 2, 12, 12))
        individual = catalog.create_individual(species.id, code=f"CA-{index + 1:03d}")
        assert individual.id is not None
        catalog.link_observation(observation.id, individual.id)
        ids.append(observation.id)

    screen = IdentificationScreen(app_state)
    qtbot.addWidget(screen)
    screen._query_observation_id = ids[0]
    screen._update_action_buttons()
    # The button says what it will do rather than promising a "new" individual it cannot create.
    assert "keep CA-001" in screen.new_button.text()

    before = catalog.individual_count()
    screen.mark_new()

    assert catalog.individual_count() == before  # nothing minted, nothing duplicated
    query = catalog.get_observation(ids[0])
    assert query is not None
    kept = catalog.get_individual(query.individual_id or 0)
    assert kept is not None and kept.code == "CA-001"  # the name the researcher wanted kept
    assert "Kept as individual CA-001" in screen.status_label.text()
    assert "CA-001" in screen.toast.text()  # and it is impossible to miss


def test_mark_new_button_names_the_pending_code_it_would_create(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    from herpetoid.application.catalog_service import PENDING_CODE_KEY
    from herpetoid.domain import PluginRef
    from herpetoid.gui.screens.identification import IdentificationScreen

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    source = tmp_path / "a.png"
    _write_image(source)
    observation = catalog.import_observation(
        species.id, [source], measurements={PENDING_CODE_KEY: "CA-042"}
    )
    assert observation.id is not None

    screen = IdentificationScreen(app_state)
    qtbot.addWidget(screen)
    screen._query_observation_id = observation.id
    screen._update_action_buttons()
    assert "CA-042" in screen.new_button.text()  # the code it will actually create

    screen.mark_new()
    created = catalog.find_individual_by_code(species.id, "CA-042")
    assert created is not None
    assert "Created individual CA-042" in screen.status_label.text()


def _identifiable_project(app_state, tmp_path: Path, count: int = 3) -> list[int]:
    """A project of cataloged captures, each with a marked region — ready to identify."""
    from herpetoid.api import ROI
    from herpetoid.domain import PluginRef

    app_state.create_project(tmp_path / "proj", "P")
    catalog = app_state.catalog
    assert catalog is not None
    species = catalog.ensure_species(
        "Calotriton asper", module=PluginRef("calotriton_asper", "1.0")
    )
    assert species.id is not None
    ids: list[int] = []
    for index in range(count):
        source = tmp_path / f"{index}.png"
        _write_image(source, size=48)
        observation = catalog.import_observation(species.id, [source], observer="AL")
        assert observation.id is not None
        image = catalog.images_for(observation.id)[0]
        assert image.id is not None
        catalog.set_image_roi(image.id, ROI.rectangle(4, 4, 40, 40))
        individual = catalog.create_individual(species.id, code=f"CA-{index + 1:03d}")
        assert individual.id is not None
        catalog.link_observation(observation.id, individual.id)
        ids.append(observation.id)
    return ids


def test_identification_advances_to_the_next_capture_after_a_decision(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    """Working a season is a single pass: a decision moves on, it does not go back to the top."""
    from herpetoid.gui.screens.identification import IdentificationScreen

    ids = _identifiable_project(app_state, tmp_path, count=3)
    catalog = app_state.catalog
    assert catalog is not None
    screen = IdentificationScreen(app_state)
    qtbot.addWidget(screen)

    screen.query_combo.setCurrentIndex(screen.query_combo.findData(ids[0]))
    screen.identify()
    assert screen.query_combo.currentData() == ids[0]

    screen.mark_new()  # "not a recapture" — it is already CA-001
    assert screen.query_combo.currentData() == ids[1]  # ...and we are on the next one
    assert "Next: CA-002" in screen.status_label.text()

    # The ranking on screen belonged to the previous query: it must not linger and invite a
    # decision about the wrong pair.
    assert screen._candidates == []
    assert screen._query_observation_id is None

    screen.identify()
    screen.mark_new()
    assert screen.query_combo.currentData() == ids[2]

    # The last one to assess: there is nowhere further to go, and it says so.
    screen.identify()
    screen.mark_new()
    assert len(catalog.identified_observation_ids()) == 3
    assert "Every capture" in screen.toast.text()


def test_the_query_selection_survives_an_unrelated_refresh(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    """A save elsewhere in the app must not throw the reviewer back to the first capture."""
    from herpetoid.gui.screens.identification import IdentificationScreen

    ids = _identifiable_project(app_state, tmp_path, count=3)
    screen = IdentificationScreen(app_state)
    qtbot.addWidget(screen)

    screen.query_combo.setCurrentIndex(screen.query_combo.findData(ids[2]))
    app_state.project_changed.emit()  # e.g. an observation saved on another tab
    assert screen.query_combo.currentData() == ids[2]


def test_the_comparison_names_each_pattern_and_pops_out_both_photographs(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    """Which side is the query and which the possible recapture, and the frames they came from."""
    from herpetoid.gui.screens.identification import IdentificationScreen

    ids = _identifiable_project(app_state, tmp_path, count=2)
    screen = IdentificationScreen(app_state)
    qtbot.addWidget(screen)
    screen.query_combo.setCurrentIndex(screen.query_combo.findData(ids[0]))
    screen.identify()
    assert screen._candidates, "no candidate to compare against"

    pair = screen.overlay.pair()
    assert pair is not None
    assert pair[0].title == "Query · CA-001"
    assert pair[1].title == "Candidate · CA-002"
    assert pair[0].image is not None and pair[1].image is not None  # the whole photographs

    for side, expected in ((0, "Query · CA-001"), (1, "Candidate · CA-002")):
        window = screen.overlay.show_full_image(side)
        assert window is not None
        qtbot.addWidget(window)
        assert window.windowTitle() == expected
        assert window.viewer.has_image()
        window.close()


def test_the_roi_preview_pops_out_the_photograph_it_was_cropped_from(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    from herpetoid.gui.screens.identification import IdentificationScreen

    ids = _identifiable_project(app_state, tmp_path, count=2)
    screen = IdentificationScreen(app_state)
    qtbot.addWidget(screen)
    screen.query_combo.setCurrentIndex(screen.query_combo.findData(ids[0]))
    screen.identify()

    preview = screen.query_panel.roi
    assert preview.has_full_image()
    window = preview.show_full_image()
    assert window is not None
    qtbot.addWidget(window)
    assert window.windowTitle() == "CA-001 · Observation 1"
    assert window.viewer.has_image()
    window.close()

    preview.clear_preview()
    assert not preview.has_full_image()
    assert preview.show_full_image() is None  # nothing to show, and no crash


def test_roi_outline_marks_the_region_without_touching_the_rest() -> None:
    from herpetoid.api import ROI
    from herpetoid.gui.widgets.full_image import with_roi_outline

    image = np.zeros((80, 80, 3), np.uint8)
    outlined = with_roi_outline(image, ROI.rectangle(20, 20, 40, 40))
    assert outlined.shape == image.shape
    assert outlined.any()  # the outline was drawn
    assert not outlined[0:5, 0:5].any()  # ...and only where the region is
    assert np.array_equal(with_roi_outline(image, None), image)  # no ROI: the frame, untouched


def test_match_captions_are_styled_widgets_under_each_panel(qtbot) -> None:
    """The names are interface chips, not pixels burnt into the picture."""
    import numpy as np

    from herpetoid.gui.widgets.match_overlay import MatchOverlayViewer, SourceImage

    overlay = MatchOverlayViewer()
    qtbot.addWidget(overlay)
    assert not overlay._caption_row.isVisibleTo(overlay)  # nothing to name yet

    photo = np.zeros((20, 20, 3), np.uint8)
    overlay.set_pair(SourceImage("Query · CA-001", photo), SourceImage("Candidate · CA-002", photo))
    assert overlay.left_caption.text() == "Query · CA-001"
    assert overlay.right_caption.text() == "Candidate · CA-002"
    assert overlay._caption_row.isVisibleTo(overlay)
    # Styled by the theme as the Mode switch's cells are, and centred in its own cell.
    assert overlay.left_caption.objectName() == "matchCaption"
    assert overlay.left_caption.alignment() & Qt.AlignmentFlag.AlignCenter

    overlay.clear()
    assert not overlay._caption_row.isVisibleTo(overlay)


def test_the_theme_styles_the_match_captions_like_the_mode_switch() -> None:
    from herpetoid.gui.theme import STYLES, _stylesheet

    for style in STYLES:
        for mode in ("light", "dark"):
            sheet = _stylesheet(style, mode)
            assert "QLabel#matchCaption" in sheet
            assert "QPushButton#modeSwitch" in sheet  # the cell it is meant to match


def test_turning_a_capture_keeps_it_turned_everywhere_and_carries_its_region(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    """The whole point: a capture turned upright in the editor stays that way in identification.

    Two animals photographed head-to-tail cannot be compared side by side, so the correction has to
    travel with the capture — and the marked region has to travel with it, or it lands off the animal.
    """
    from herpetoid.api import ROI
    from herpetoid.gui.screens.observations import ObservationsScreen
    from herpetoid.gui.widgets.observation_panel import observation_image_and_roi

    ids = _identifiable_project(app_state, tmp_path, count=2)
    catalog = app_state.catalog
    assert catalog is not None
    image = catalog.images_for(ids[0])[0]
    assert image.id is not None
    catalog.set_image_roi(image.id, ROI.rectangle(4, 4, 20, 10))  # a wide box on a 48x48 photo
    app_state.project_changed.emit()

    editor = ObservationsScreen(app_state)
    qtbot.addWidget(editor)
    editor.select_observation(ids[0])
    shown = editor.viewer.image()
    assert shown is not None and shown.shape[:2] == (48, 48)
    before = editor.viewer.roi()
    assert before is not None and before.bounding_box() == (4, 4, 20, 10)

    editor.rotate_current_image(90)

    # Persisted at once, like every other change in this application.
    assert catalog.images_for(ids[0])[0].rotation == 90
    turned = editor.viewer.roi()
    assert turned is not None
    assert turned.bounding_box() == (33, 4, 10, 20)  # the box turned with the picture

    # Every other view loads it the same way up, region included.
    array, roi = observation_image_and_roi(app_state, ids[0])
    assert array is not None and roi is not None
    assert roi.bounding_box() == turned.bounding_box()
    assert array.shape[:2] == (48, 48)  # square here, so check the region did the moving

    # Saving stores the region back in the file's own coordinates, so turning does not make it
    # creep across the animal a little further each time.
    editor.save()
    assert catalog.get_image_roi(image.id).bounding_box() == (4, 4, 20, 10)
    assert catalog.images_for(ids[0])[0].rotation == 90  # ...and the turn is still there


def test_a_tab_already_open_on_the_capture_picks_up_the_turn(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    """A screen sitting on the capture must not keep showing it the old way up.

    Caught by looking at a screenshot, not by a test: the Identification tab held the picture it had
    loaded before the turn, because nothing told it anything had changed.
    """
    from herpetoid.gui.screens.identification import IdentificationScreen
    from herpetoid.gui.screens.observations import ObservationsScreen

    ids = _identifiable_project(app_state, tmp_path, count=2)
    identification = IdentificationScreen(app_state)
    qtbot.addWidget(identification)
    identification.query_combo.setCurrentIndex(identification.query_combo.findData(ids[0]))
    before = identification.query_panel.viewer.image_shape()
    assert before is not None

    editor = ObservationsScreen(app_state)
    qtbot.addWidget(editor)
    editor.select_observation(ids[0])
    editor.rotate_current_image(90)

    # ...without anyone touching the Identification tab.
    assert identification.query_combo.currentData() == ids[0]
    assert identification.query_panel.viewer.image_shape() == (before[1], before[0])


def test_turning_a_capture_that_is_already_identified_keeps_its_identity(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    """Rotating is a viewing correction, not a re-identification: nothing about the animal changes."""
    from herpetoid.gui.screens.observations import ObservationsScreen

    ids = _identifiable_project(app_state, tmp_path, count=2)
    catalog = app_state.catalog
    assert catalog is not None
    before = catalog.get_observation(ids[0])
    assert before is not None and before.individual_id is not None

    editor = ObservationsScreen(app_state)
    qtbot.addWidget(editor)
    editor.select_observation(ids[0])
    editor.rotate_current_image(180)
    editor.rotate_current_image(180)  # ...all the way back round

    after = catalog.get_observation(ids[0])
    assert after is not None and after.individual_id == before.individual_id
    assert catalog.images_for(ids[0])[0].rotation == 0
    roi = editor.viewer.roi()
    assert roi is not None
    assert roi.bounding_box() == (4, 4, 40, 40)  # two half turns leave the region where it was


def test_an_unsaved_region_survives_a_turn(app_state: AppState, tmp_path: Path, qtbot) -> None:
    """Rotating must never cost work in progress."""
    from herpetoid.api import ROI
    from herpetoid.gui.screens.observations import ObservationsScreen

    ids = _identifiable_project(app_state, tmp_path, count=1)
    editor = ObservationsScreen(app_state)
    qtbot.addWidget(editor)
    editor.select_observation(ids[0])
    editor.viewer.set_roi(ROI.rectangle(2, 6, 10, 4))  # drawn, not saved

    editor.rotate_current_image(90)

    turned = editor.viewer.roi()
    assert turned is not None
    assert turned.bounding_box() == (37, 2, 4, 10)


def test_the_query_panel_can_turn_the_capture_and_the_turn_sticks(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    """The other place a reviewer notices one animal is head-up and the other head-down."""
    from herpetoid.gui.screens.identification import IdentificationScreen
    from herpetoid.gui.screens.observations import ObservationsScreen

    ids = _identifiable_project(app_state, tmp_path, count=2)
    catalog = app_state.catalog
    assert catalog is not None

    identification = IdentificationScreen(app_state)
    qtbot.addWidget(identification)
    identification.query_combo.setCurrentIndex(identification.query_combo.findData(ids[0]))
    assert identification.query_panel.observation_id == ids[0]
    before = identification.query_panel.viewer.image_shape()
    assert before is not None

    # The toolbar only asks; the screen records it.
    identification.query_panel.viewer.rotation_requested.emit(90)

    assert catalog.images_for(ids[0])[0].rotation == 90
    assert identification.query_panel.viewer.image_shape() == (before[1], before[0])

    # ...and the editor, the other owner of this capture, opens it the same way up.
    editor = ObservationsScreen(app_state)
    qtbot.addWidget(editor)
    editor.select_observation(ids[0])
    shown = editor.viewer.image()
    assert shown is not None and shown.shape[:2] == (before[1], before[0])
    roi = editor.viewer.roi()
    # A quarter turn of a 48x48 photo: the box lands at (3, 4) -- the ``h - 1 - y`` term is
    # the last column, not a rounding slip.
    assert roi is not None and roi.bounding_box() == (3, 4, 40, 40)


def test_turning_the_query_rebuilds_the_evidence_it_invalidates(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    """Candidates computed from the old orientation must not sit beside the new pictures."""
    from herpetoid.gui.screens.identification import IdentificationScreen

    ids = _identifiable_project(app_state, tmp_path, count=2)
    catalog = app_state.catalog
    assert catalog is not None
    screen = IdentificationScreen(app_state)
    qtbot.addWidget(screen)
    screen.query_combo.setCurrentIndex(screen.query_combo.findData(ids[0]))
    screen.identify()
    assert screen._candidates, "nothing to rebuild"

    screen.rotate_shown_image(90)

    assert catalog.images_for(ids[0])[0].rotation == 90
    # Re-run for the same query, so the match evidence matches the pictures beside it.
    assert screen._query_observation_id == ids[0]
    assert screen._candidates


def test_turning_before_any_run_does_not_start_one(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    from herpetoid.gui.screens.identification import IdentificationScreen

    ids = _identifiable_project(app_state, tmp_path, count=2)
    catalog = app_state.catalog
    assert catalog is not None
    screen = IdentificationScreen(app_state)
    qtbot.addWidget(screen)
    screen.query_combo.setCurrentIndex(screen.query_combo.findData(ids[0]))

    screen.rotate_shown_image(180)

    assert catalog.images_for(ids[0])[0].rotation == 180
    assert screen._candidates == []  # turning is not a request to identify
    assert screen._query_observation_id is None


def test_compare_mode_keeps_its_pair_when_the_capture_is_turned(
    app_state: AppState, tmp_path: Path, qtbot
) -> None:
    """A refresh must not silently swap which two captures are being compared."""
    from herpetoid.gui.screens.identification import IdentificationScreen

    ids = _identifiable_project(app_state, tmp_path, count=3)
    screen = IdentificationScreen(app_state)
    qtbot.addWidget(screen)
    screen.set_mode("compare")
    screen.obs_a_combo.setCurrentIndex(screen.obs_a_combo.findData(ids[1]))
    screen.obs_b_combo.setCurrentIndex(screen.obs_b_combo.findData(ids[2]))
    assert screen.query_panel.observation_id == ids[1]

    screen.rotate_shown_image(90)

    assert screen.obs_a_combo.currentData() == ids[1]
    assert screen.obs_b_combo.currentData() == ids[2]


def test_only_the_viewers_that_ask_for_the_turn_toolbar_get_one(qtbot) -> None:
    """The match composite is two pictures in one frame; turning it would mean nothing."""
    from herpetoid.gui.widgets.image_viewer import ImageViewer
    from herpetoid.gui.widgets.match_overlay import MatchOverlayViewer
    from herpetoid.gui.widgets.observation_panel import ObservationPanel
    from herpetoid.gui.widgets.roi_image_viewer import RoiImageViewer

    plain = ImageViewer()
    qtbot.addWidget(plain)
    assert plain._view_tools is None

    editor_viewer = RoiImageViewer()  # the editor always has them
    qtbot.addWidget(editor_viewer)
    assert editor_viewer._view_tools is not None

    panel = ObservationPanel("Query observation", view_tools=True)
    qtbot.addWidget(panel)
    assert panel.viewer._view_tools is not None
    plain_panel = ObservationPanel("Plain")
    qtbot.addWidget(plain_panel)
    assert plain_panel.viewer._view_tools is None

    overlay = MatchOverlayViewer()
    qtbot.addWidget(overlay)
    assert overlay.viewer._view_tools is None
