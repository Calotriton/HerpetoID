"""A compact, read-only key/value table for showing an observation's or individual's information.

The measurement rows are driven by what the *species module* declares (``define_observation_fields``),
so each species shows its own fields with the right labels and units — Core hard-codes none of them.
"""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from herpetoid.api import FieldDefinition
from herpetoid.domain import Observation
from herpetoid.gui.state import AppState


def species_field_definitions(state: AppState, species_id: int) -> list[FieldDefinition]:
    """The observation fields a species declares, or ``[]`` if unavailable (a broken/absent module)."""
    catalog = state.catalog
    if catalog is None:
        return []
    species = catalog.get_species(species_id)
    if species is None or species.module is None:
        return []
    if state.registry.module(species.module.plugin_id) is None:
        return []
    try:
        module = state.registry.create_module(species.module.plugin_id)
        return list(module.define_observation_fields())
    except Exception:  # a broken module must not break the screen
        return []


def format_date(value: date | datetime | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return str(value)


def measurement_rows(
    observation: Observation, fields: list[FieldDefinition]
) -> list[tuple[str, str]]:
    """Declared measurement fields that have a value on this observation, with units."""
    rows: list[tuple[str, str]] = []
    for field in sorted(fields, key=lambda f: f.order):
        value = observation.measurements.get(field.key)
        if value is None or value == "":
            continue
        rows.append((field.label, f"{value} {field.unit}".strip() if field.unit else f"{value}"))
    return rows


def location_rows(observation: Observation) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    location = observation.location
    if location.name:
        rows.append(("Location", location.name))
    if location.latitude is not None and location.longitude is not None:
        rows.append(("Coordinates", f"{location.latitude:.4f}, {location.longitude:.4f}"))
    return rows


def observation_info_rows(
    observation: Observation,
    fields: list[FieldDefinition],
    *,
    individual_code: str | None = None,
) -> list[tuple[str, str]]:
    """Full rows for an observation panel: identity, capture metadata, location and measurements."""
    rows: list[tuple[str, str]] = []
    if individual_code:
        rows.append(("Individual", individual_code))
    if observation.observer:
        rows.append(("Observer", observation.observer))
    observed = format_date(observation.observed_at)
    if observed:
        rows.append(("Date", observed))
    rows.extend(location_rows(observation))
    rows.extend(measurement_rows(observation, fields))
    return rows


class InfoTable(QTableWidget):
    """A borderless two-column (Field / Value) read-only table."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels(["Field", "Value"])
        self.verticalHeader().setVisible(False)
        header = self.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setVisible(False)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setShowGrid(False)

    def show_rows(self, rows: list[tuple[str, str]]) -> None:
        self.setRowCount(len(rows))
        for row, (key, value) in enumerate(rows):
            field_item = QTableWidgetItem(str(key))
            field_item.setForeground(self.palette().mid())
            self.setItem(row, 0, field_item)
            self.setItem(row, 1, QTableWidgetItem(str(value)))

    def clear_rows(self) -> None:
        self.setRowCount(0)
