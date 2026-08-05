"""Per-OS application data locations (Windows: under %APPDATA% / %LOCALAPPDATA%), plus the
containment rule for bundle-relative paths."""

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


class BundlePathError(ValueError):
    """Raised when a bundle-relative path would resolve outside its project bundle."""


def resolve_in_bundle(root: Path, rel_path: str) -> Path:
    """Resolve a bundle-relative path against ``root``, refusing anything that escapes the bundle.

    Project bundles are portable and meant to be **shared** between researchers, so everything a
    bundle carries -- including the paths stored in its ``project.db`` -- is untrusted input. Without
    this check, a bundle whose image rows say ``../../../secrets.png`` (or an absolute path, or a
    symlink pointing out of the bundle) would make HerpetoID read files from anywhere on the opener's
    machine and embed them in exported reports. Every bundle-relative path goes through here.
    """
    text = str(rel_path).strip()
    if not text:
        raise BundlePathError("bundle path is empty")
    # Normalize separators so a Windows-style path is judged by the same rules on every OS.
    candidate = Path(text.replace("\\", "/"))
    if candidate.is_absolute() or candidate.drive or candidate.anchor:
        raise BundlePathError(f"bundle path must be relative, got {rel_path!r}")
    if any(part == ".." for part in candidate.parts):
        raise BundlePathError(f"bundle path must not traverse upwards, got {rel_path!r}")
    resolved_root = root.resolve()
    # resolve() follows symlinks, so a link inside the bundle pointing outside is caught here too.
    resolved = (resolved_root / candidate).resolve()
    if not resolved.is_relative_to(resolved_root):
        raise BundlePathError(f"bundle path escapes the project bundle, got {rel_path!r}")
    return resolved
