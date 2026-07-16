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
    qtbot.addWidget(screen)
    assert screen.species_combo.count() >= 1  # Calotriton asper from the registry

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
    assert "2026-05-10" in screen.obs_position_label.text()
    assert not screen.prev_button.isEnabled()
    assert screen.next_button.isEnabled()

    screen._step_observation(1)  # arrow to the second observation
    assert "Observation 2 of 2" in screen.obs_position_label.text()
    assert "2026-05-20" in screen.obs_position_label.text()
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

    # Marking again must NOT mint a duplicate individual.
    screen._query_observation_id = obs.id
    screen.mark_new()
    assert catalog.individual_count() == 1
    assert "Already assigned" in screen.status_label.text()

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
    # The left pattern is scaled 50/40 = 1.25x to match: width 30 -> 38.
    assert composite.shape[1] == 38 + 24 + 20  # left + gap + right


def test_build_match_composite_normalizes_orientation_and_size() -> None:
    """Landscape patterns are rotated upright and both sides share one height (like-for-like pair)."""
    from herpetoid.gui.widgets.match_overlay import build_match_composite

    landscape = np.zeros((30, 40), np.uint8)  # wider than tall -> must be rotated to 40x30
    portrait = np.zeros((50, 20), np.uint8)
    corr = np.array([[39, 0, 4, 4]], float)  # top-right corner of the landscape query
    composite = build_match_composite(landscape, portrait, corr)
    assert composite.shape[0] == 50  # rotated left (40 tall) scaled up to the right's 50
    left_width = round(30 * 50 / 40)  # 38 after the 1.25x scale
    assert composite.shape[1] == left_width + 24 + 20
    # The overlay must still land on the canvas: something was drawn (composite differs from plain).
    plain = build_match_composite(landscape, portrait, corr, show_lines=False, show_points=False)
    assert not np.array_equal(plain, composite)
    # And both sides are fully painted (no untouched background stripe below either pattern).
    assert not (plain[:, :left_width] == 245).all(axis=2).any()  # left column fully covered
    assert not (plain[:, left_width + 24 :] == 245).all(axis=2).any()  # right column fully covered


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
