"""Per-OS application data locations (Windows: under %APPDATA% / %LOCALAPPDATA%)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from platformdirs import PlatformDirs

_DIRS = PlatformDirs(appname="HerpetoID", appauthor="HerpetoID")


@dataclass(frozen=True, slots=True)
class AppPaths:
    """Resolved application directories and files."""

    config_dir: Path
    data_dir: Path
    log_dir: Path
    plugins_dir: Path  # user drop-in plugins folder
    settings_file: Path


def app_paths() -> AppPaths:
    config_dir = Path(_DIRS.user_config_dir)
    data_dir = Path(_DIRS.user_data_dir)
    log_dir = Path(_DIRS.user_log_dir)
    return AppPaths(
        config_dir=config_dir,
        data_dir=data_dir,
        log_dir=log_dir,
        plugins_dir=data_dir / "plugins",
        settings_file=config_dir / "settings.json",
    )
