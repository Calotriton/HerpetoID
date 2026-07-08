"""Application entry point: build the QApplication, apply theme, discover plugins, show the window."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication

from herpetoid.application.registry import PluginRegistry
from herpetoid.application.settings import SettingsService
from herpetoid.infrastructure.logging_setup import configure_logging
from herpetoid.infrastructure.paths import app_paths
from herpetoid.infrastructure.plugin_discovery import discover_entry_points, discover_folder
from herpetoid.infrastructure.settings_store import JsonSettingsStore

from .main_window import MainWindow
from .theme import ThemeManager


def build_registry() -> PluginRegistry:
    """Discover plugins from entry points and the user drop-in folder."""
    registry = PluginRegistry()
    discover_entry_points(registry)
    plugins_dir = app_paths().plugins_dir
    if plugins_dir.exists():
        discover_folder(registry, plugins_dir)
    return registry


def run(argv: list[str] | None = None) -> int:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(argv or [])
    paths = app_paths()
    configure_logging(paths.log_dir)
    settings = SettingsService(JsonSettingsStore(paths.settings_file))
    ThemeManager(app).apply(settings.settings.theme)

    window = MainWindow(build_registry())
    window.show()
    return app.exec()
