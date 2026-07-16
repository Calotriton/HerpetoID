"""A form widget generated from declared :class:`FieldDefinition`s.

This is how Core "auto-generates the GUI" without hard-coding any observation fields: given a species'
declared fields, it builds the right editor per field type and reads/writes/validates values.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Any

from PySide6.QtCore import QDate
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDoubleSpinBox,
    QFormLayout,
    QLineEdit,
    QSpinBox,
    QWidget,
)

from herpetoid.api import FieldDefinition, FieldType, ValidationResult

_NUMERIC_RANGE = 1_000_000_000


class DynamicForm(QWidget):
    """Builds editors for a list of fields and reads/writes/validates their values."""

    def __init__(self, fields: Sequence[FieldDefinition]) -> None:
        super().__init__()
        self._fields = sorted(fields, key=lambda f: f.order)
        # Heterogeneous Qt editors keyed by field; typed Any so per-type methods (value/text/...) are ok.
        self._widgets: dict[str, Any] = {}
        form = QFormLayout(self)
        for field in self._fields:
            widget = self._make_widget(field)
            self._widgets[field.key] = widget
            label = field.label + (f" ({field.unit})" if field.unit else "")
            if field.validation.required:
                label += " *"
            form.addRow(label, widget)

    @staticmethod
    def _make_widget(field: FieldDefinition) -> QWidget:
        # Numeric editors start *empty* (the range minimum is a sentinel rendered as blank text)
        # instead of showing a misleading default of 0 — an untouched field reads back as None.
        match field.type:
            case FieldType.INTEGER:
                spin = QSpinBox()
                spin.setRange(-_NUMERIC_RANGE, _NUMERIC_RANGE)
                spin.setSpecialValueText(" ")
                spin.setValue(spin.minimum())
                return spin
            case FieldType.FLOAT:
                dspin = QDoubleSpinBox()
                dspin.setRange(-_NUMERIC_RANGE, _NUMERIC_RANGE)
                dspin.setDecimals(3)
                dspin.setSpecialValueText(" ")
                dspin.setValue(dspin.minimum())
                return dspin
            case FieldType.BOOLEAN:
                return QCheckBox()
            case FieldType.CHOICE:
                combo = QComboBox()
                combo.addItem("")
                combo.addItems(list(field.choices or ()))
                return combo
            case FieldType.DATE | FieldType.DATETIME:
                edit = QDateEdit()
                edit.setCalendarPopup(True)
                edit.setDate(QDate.currentDate())
                return edit
            case _:
                return QLineEdit()

    def values(self) -> dict[str, Any]:
        return {field.key: self._read(field) for field in self._fields}

    def _read(self, field: FieldDefinition) -> Any:
        widget = self._widgets[field.key]
        match field.type:
            case FieldType.INTEGER | FieldType.FLOAT:
                value = widget.value()
                return None if value == widget.minimum() else value  # untouched -> no value
            case FieldType.BOOLEAN:
                return widget.isChecked()
            case FieldType.CHOICE:
                return widget.currentText() or None
            case FieldType.DATE | FieldType.DATETIME:
                return widget.date().toPython()
            case _:
                return widget.text().strip() or None

    def set_values(self, values: dict[str, Any]) -> None:
        for field in self._fields:
            if field.key not in values:
                continue
            value = values[field.key]
            if value is None:
                continue
            widget = self._widgets[field.key]
            match field.type:
                case FieldType.INTEGER:
                    widget.setValue(int(value))
                case FieldType.FLOAT:
                    widget.setValue(float(value))
                case FieldType.BOOLEAN:
                    widget.setChecked(bool(value))
                case FieldType.CHOICE:
                    widget.setCurrentText(str(value))
                case FieldType.DATE | FieldType.DATETIME:
                    if isinstance(value, (date, datetime)):
                        widget.setDate(QDate(value.year, value.month, value.day))
                case _:
                    widget.setText(str(value))

    def missing_labels(self) -> list[str]:
        """Labels of the fields the user has not filled in (checkboxes always count as filled)."""
        values = self.values()
        return [field.label for field in self._fields if values[field.key] is None]

    def validate(self) -> ValidationResult:
        values = self.values()
        result = ValidationResult.success()
        for field in self._fields:
            result = result.merge(field.validate_value(values[field.key]))
        return result
