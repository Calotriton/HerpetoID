"""Application entry point: build the QApplication, wire state, apply theme, show the window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QApplication

from herpetoid import __version__
from herpetoid.application.project_service import ProjectService
from herpetoid.application.registry import PluginRegistry
from herpetoid.application.settings import SettingsService
from herpetoid.infrastructure.logging_setup import configure_logging
from herpetoid.infrastructure.paths import app_paths
from herpetoid.infrastructure.plugin_discovery import discover_entry_points, discover_folder
from herpetoid.infrastructure.settings_store import JsonSettingsStore

from .main_window import MainWindow
from .state import AppState
from .theme import ThemeManager


def build_registry() -> PluginRegistry:
    """Discover plugins from entry points and the user drop-in folder."""
    registry = PluginRegistry()
    discover_entry_points(registry)
    plugins_dir = app_paths().plugins_dir
    if plugins_dir.exists():
        discover_folder(registry, plugins_dir)
    return registry


def build_app_state() -> AppState:
    settings = SettingsService(JsonSettingsStore(app_paths().settings_file))
    return AppState(
        registry=build_registry(),
        project_service=ProjectService(app_version=__version__),
        settings=settings,
    )


def reopen_last_project(state: AppState) -> None:
    """Reopen the most recent still-existing project so work continues where the user left off."""
    for path in state.settings.settings.recent_projects:
        bundle = Path(path)
        if ProjectService.is_project_bundle(bundle):
            try:
                state.open_project(bundle)
                return
            except (FileNotFoundError, ValueError):
                continue


def run(argv: list[str] | None = None) -> int:
    existing = QApplication.instance()
    app = existing if isinstance(existing, QApplication) else QApplication(argv or [])
    configure_logging(app_paths().log_dir)

    state = build_app_state()
    ThemeManager(app).apply(state.settings.settings.theme, state.settings.settings.style)
    reopen_last_project(state)  # autosave-friendly: pick up the last project on launch

    window = MainWindow(state)
    window.show()
    return app.exec()
