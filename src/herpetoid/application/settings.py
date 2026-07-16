"""Application settings model, store port, and service."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

_MAX_RECENT = 10


@dataclass(slots=True)
class Settings:
    """User-level application settings (persisted outside any project bundle)."""

    theme: str = "system"  # 'system' | 'light' | 'dark'
    style: str = "teal"  # visual style preset id (see herpetoid.gui.theme.STYLES)
    language: str = "en"
    default_top_k: int = 3
    default_algorithm_id: str = ""  # last algorithm picked on the Identification tab
    recent_projects: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "theme": self.theme,
            "style": self.style,
            "language": self.language,
            "default_top_k": self.default_top_k,
            "default_algorithm_id": self.default_algorithm_id,
            "recent_projects": list(self.recent_projects),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Settings:
        return cls(
            theme=str(data.get("theme", "system")),
            style=str(data.get("style", "teal")),
            language=str(data.get("language", "en")),
            default_top_k=int(data.get("default_top_k", 3)),
            default_algorithm_id=str(data.get("default_algorithm_id", "")),
            recent_projects=[str(p) for p in data.get("recent_projects", [])],
        )


class SettingsStore(Protocol):
    """Loads and persists :class:`Settings`."""

    def load(self) -> Settings: ...

    def save(self, settings: Settings) -> None: ...


class SettingsService:
    """Holds the current settings and persists changes through a store."""

    def __init__(self, store: SettingsStore) -> None:
        self._store = store
        self._settings = store.load()

    @property
    def settings(self) -> Settings:
        return self._settings

    def save(self, settings: Settings) -> None:
        self._settings = settings
        self._store.save(settings)

    def set_theme(self, theme: str) -> None:
        self._settings.theme = theme
        self._store.save(self._settings)

    def set_style(self, style: str) -> None:
        self._settings.style = style
        self._store.save(self._settings)

    def set_default_algorithm(self, algorithm_id: str) -> None:
        self._settings.default_algorithm_id = algorithm_id
        self._store.save(self._settings)

    def add_recent_project(self, path: str) -> None:
        """Record a project path as most-recent (de-duplicated, capped)."""
        remaining = [p for p in self._settings.recent_projects if p != path]
        self._settings.recent_projects = [path, *remaining][:_MAX_RECENT]
        self._store.save(self._settings)

    def prune_recent_projects(self, keep: Callable[[str], bool]) -> list[str]:
        """Drop recent-project entries that no longer satisfy ``keep`` (e.g. deleted folders)."""
        kept = [p for p in self._settings.recent_projects if keep(p)]
        if kept != self._settings.recent_projects:
            self._settings.recent_projects = kept
            self._store.save(self._settings)
        return kept
