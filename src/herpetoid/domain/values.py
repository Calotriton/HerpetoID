"""Immutable domain value objects."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Location:
    """An optional geographic location for an observation."""

    latitude: float | None = None
    longitude: float | None = None
    accuracy_m: float | None = None
    name: str | None = None

    def __post_init__(self) -> None:
        if self.latitude is not None and not -90.0 <= self.latitude <= 90.0:
            raise ValueError(f"latitude out of range: {self.latitude}")
        if self.longitude is not None and not -180.0 <= self.longitude <= 180.0:
            raise ValueError(f"longitude out of range: {self.longitude}")

    @property
    def is_empty(self) -> bool:
        return self.latitude is None and self.longitude is None and not self.name

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None and self.longitude is not None


@dataclass(frozen=True, slots=True)
class PluginRef:
    """A reference to a plugin by id and version, recorded for provenance/reproducibility."""

    plugin_id: str
    version: str = ""

    def __str__(self) -> str:
        return f"{self.plugin_id}@{self.version}" if self.version else self.plugin_id
