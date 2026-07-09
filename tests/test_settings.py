"""Tests for settings persistence, app paths, and logging setup."""

from __future__ import annotations

import logging
from pathlib import Path

from herpetoid.application.settings import Settings, SettingsService
from herpetoid.infrastructure.logging_setup import configure_logging
from herpetoid.infrastructure.paths import app_paths
from herpetoid.infrastructure.settings_store import JsonSettingsStore


def test_settings_defaults_and_roundtrip(tmp_path: Path) -> None:
    store = JsonSettingsStore(tmp_path / "settings.json")
    assert store.load() == Settings()  # defaults when the file is missing
    saved = Settings(theme="dark", default_top_k=5, recent_projects=["a", "b"])
    store.save(saved)
    assert store.load() == saved


def test_settings_service_recent_projects(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    service = SettingsService(JsonSettingsStore(path))
    service.add_recent_project("p1")
    service.add_recent_project("p2")
    service.add_recent_project("p1")  # moves to front, de-duplicated
    assert service.settings.recent_projects == ["p1", "p2"]
    service.set_theme("light")

    reloaded = SettingsService(JsonSettingsStore(path))
    assert reloaded.settings.theme == "light"
    assert reloaded.settings.recent_projects == ["p1", "p2"]


def test_prune_recent_projects_drops_missing(tmp_path: Path) -> None:
    service = SettingsService(JsonSettingsStore(tmp_path / "settings.json"))
    service.add_recent_project("gone")
    service.add_recent_project("kept")
    kept = service.prune_recent_projects(lambda p: p == "kept")
    assert kept == ["kept"]
    assert service.settings.recent_projects == ["kept"]  # persisted


def test_app_paths() -> None:
    paths = app_paths()
    assert "HerpetoID" in str(paths.settings_file)
    assert paths.settings_file.name == "settings.json"
    assert paths.plugins_dir.name == "plugins"


def test_configure_logging_writes_to_file(tmp_path: Path) -> None:
    logger = logging.getLogger("herpetoid")
    original_handlers = list(logger.handlers)
    try:
        configure_logging(tmp_path / "logs")
        logging.getLogger("herpetoid.test").warning("hello-from-test")
        for handler in logger.handlers:
            handler.flush()
        log_file = tmp_path / "logs" / "herpetoid.log"
        assert log_file.exists()
        assert "hello-from-test" in log_file.read_text(encoding="utf-8")
    finally:
        for handler in list(logger.handlers):
            if handler not in original_handlers:
                logger.removeHandler(handler)
                handler.close()
