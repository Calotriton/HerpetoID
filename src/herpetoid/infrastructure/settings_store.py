"""JSON-backed settings store."""

from __future__ import annotations

import json
from pathlib import Path

from herpetoid.application.settings import Settings


class JsonSettingsStore:
    """Reads/writes :class:`Settings` as a JSON file (defaults when missing or unreadable)."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def load(self) -> Settings:
        if not self._path.exists():
            return Settings()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return Settings()
        if not isinstance(data, dict):
            return Settings()
        return Settings.from_dict(data)

    def save(self, settings: Settings) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(settings.to_dict(), indent=2), encoding="utf-8")
