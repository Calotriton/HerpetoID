"""Data export: flatten a catalog and dispatch to registered exporters.

The pure row-flattening lives here (application layer); concrete file writers (CSV / Excel / JSON) live
in the infrastructure layer and implement the :class:`Exporter` port.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from herpetoid.api import FieldDefinition
from herpetoid.domain import Individual, Observation, Project, Species

_BASE_COLUMNS = [
    "observation_id",
    "species",
    "individual",
    "observer",
    "observed_at",
    "notes",
    "latitude",
    "longitude",
    "location",
]


@dataclass(slots=True)
class ExportData:
    """A snapshot of a catalog to export."""

    project: Project
    species: Sequence[Species] = ()
    individuals: Sequence[Individual] = ()
    observations: Sequence[Observation] = ()
    measurement_fields: Sequence[FieldDefinition] = ()


class Exporter(Protocol):
    """Writes an :class:`ExportData` to a file in a particular format."""

    format_id: str

    def export(self, data: ExportData, destination: Path) -> None: ...


def measurement_keys(data: ExportData) -> list[str]:
    """The ordered measurement columns: declared fields if given, else discovered from observations."""
    if data.measurement_fields:
        return [f.key for f in data.measurement_fields]
    keys: list[str] = []
    seen: set[str] = set()
    for obs in data.observations:
        for key in obs.measurements:
            if key not in seen:
                seen.add(key)
                keys.append(key)
    return keys


def observation_rows(data: ExportData) -> tuple[list[str], list[dict[str, Any]]]:
    """Flatten observations into (column names, rows), one row per observation."""
    field_keys = measurement_keys(data)
    columns = _BASE_COLUMNS + field_keys
    species_by_id = {s.id: s for s in data.species}
    individual_by_id = {i.id: i for i in data.individuals}

    rows: list[dict[str, Any]] = []
    for obs in data.observations:
        species = species_by_id.get(obs.species_id)
        individual = individual_by_id.get(obs.individual_id) if obs.individual_id else None
        row: dict[str, Any] = {
            "observation_id": obs.id,
            "species": species.scientific_name if species else "",
            "individual": individual.code if individual else "",
            "observer": obs.observer,
            "observed_at": obs.observed_at.isoformat() if obs.observed_at else "",
            "notes": obs.notes,
            "latitude": obs.location.latitude,
            "longitude": obs.location.longitude,
            "location": obs.location.name or "",
        }
        for key in field_keys:
            row[key] = obs.measurements.get(key)
        rows.append(row)
    return columns, rows


class ExportService:
    """Dispatches an export to the exporter registered for the requested format."""

    def __init__(self, exporters: Sequence[Exporter]) -> None:
        self._exporters: dict[str, Exporter] = {e.format_id: e for e in exporters}

    def available_formats(self) -> list[str]:
        return sorted(self._exporters)

    def export(self, format_id: str, data: ExportData, destination: Path) -> None:
        exporter = self._exporters.get(format_id)
        if exporter is None:
            raise KeyError(f"no exporter registered for format {format_id!r}")
        exporter.export(data, destination)
