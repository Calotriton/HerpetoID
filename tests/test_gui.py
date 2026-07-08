"""GUI tests (headless via the offscreen Qt platform + pytest-qt)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

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
    assert viewer.current_scale() > before


def test_main_window_navigation(app_state: AppState, qtbot) -> None:
    window = MainWindow(app_state)
    qtbot.addWidget(window)
    names = window.screen_names()
    assert "Home" in names
    assert "Projects" in names
    assert len(names) == 11
    assert window.current_screen_name() == "Home"
    window.navigate_to("Plugins")
    assert window.current_screen_name() == "Plugins"


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
