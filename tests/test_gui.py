"""GUI tests (headless via the offscreen Qt platform + pytest-qt)."""

from __future__ import annotations

import numpy as np
import pytest

from herpetoid.application.registry import PluginRegistry
from herpetoid.gui.main_window import MainWindow
from herpetoid.gui.screens.plugins import PluginManagerScreen
from herpetoid.gui.widgets.image_viewer import ImageViewer, ndarray_to_qimage
from herpetoid.infrastructure.plugin_discovery import discover_entry_points

pytestmark = pytest.mark.gui


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


def test_main_window_navigation(qtbot) -> None:
    registry = PluginRegistry()
    discover_entry_points(registry)
    window = MainWindow(registry)
    qtbot.addWidget(window)

    names = window.screen_names()
    assert "Home" in names
    assert "Plugins" in names
    assert len(names) == 11
    assert window.current_screen_name() == "Home"
    window.navigate_to("Plugins")
    assert window.current_screen_name() == "Plugins"


def test_plugin_manager_shows_registered_plugins(qtbot) -> None:
    registry = PluginRegistry()
    discover_entry_points(registry)
    screen = PluginManagerScreen(registry)
    qtbot.addWidget(screen)
    # The first-party ORB algorithm and Calotriton module are registered via entry points.
    assert screen.modules_table.rowCount() >= 1
    assert screen.algorithms_table.rowCount() >= 1
