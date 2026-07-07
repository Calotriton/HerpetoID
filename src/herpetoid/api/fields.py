"""Declarative observation-field definitions.

A species module declares its species-specific measurements as :class:`FieldDefinition` objects; Core
auto-generates the GUI form, validates input, and stores values in the typed EAV metadata store. Core
itself hard-codes no observation fields.
"""

from __future__ import annotations

import datetime as _dt
import re
from dataclasses import dataclass, field
from typing import Any

from .enums import FieldGroup, FieldType
from .validation import ValidationIssue, ValidationResult


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_int(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return value.is_integer()
    return False


@dataclass(frozen=True, slots=True)
class Validation:
    """Optional validation rules for a field. Empty by default (no constraints)."""

    required: bool = False
    min_value: float | None = None
    max_value: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    pattern: str | None = None  # regex, applied to TEXT values via re.fullmatch


@dataclass(frozen=True, slots=True)
class FieldDefinition:
    """A single declared observation field (the unit Core builds forms and statistics from)."""

    key: str
    label: str
    type: FieldType
    group: FieldGroup = FieldGroup.GENERAL
    unit: str | None = None
    default: Any = None
    choices: tuple[str, ...] | None = None
    validation: Validation = field(default_factory=Validation)
    help_text: str = ""
    order: int = 0
    include_in_statistics: bool = False

    def __post_init__(self) -> None:
        if not self.key:
            raise ValueError("FieldDefinition.key must be a non-empty identifier")
        if self.type in (FieldType.CHOICE, FieldType.MULTI_CHOICE) and not self.choices:
            raise ValueError(f"field {self.key!r} of type {self.type} requires 'choices'")

    def validate_value(self, value: Any) -> ValidationResult:
        """Validate one value against this field's type and rules. Pure and Qt-free."""
        rules = self.validation
        empty = value is None or (isinstance(value, str) and not value.strip())
        if empty:
            if rules.required:
                return ValidationResult.of(
                    [ValidationIssue("required", f"{self.label} is required.")]
                )
            return ValidationResult.success()

        issues: list[ValidationIssue] = []
        match self.type:
            case FieldType.INTEGER:
                if not _is_int(value):
                    issues.append(ValidationIssue("type", f"{self.label} must be a whole number."))
                else:
                    issues.extend(self._range_issues(int(value)))
            case FieldType.FLOAT:
                if not _is_number(value):
                    issues.append(ValidationIssue("type", f"{self.label} must be a number."))
                else:
                    issues.extend(self._range_issues(float(value)))
            case FieldType.BOOLEAN:
                if not isinstance(value, bool):
                    issues.append(ValidationIssue("type", f"{self.label} must be true or false."))
            case FieldType.TEXT:
                issues.extend(self._text_issues(str(value)))
            case FieldType.DATE | FieldType.DATETIME:
                if not isinstance(value, (_dt.date, _dt.datetime, str)):
                    issues.append(ValidationIssue("type", f"{self.label} must be a date."))
            case FieldType.CHOICE:
                if self.choices is not None and str(value) not in self.choices:
                    issues.append(
                        ValidationIssue("choice", f"{self.label}: {value!r} is not a valid option.")
                    )
            case FieldType.MULTI_CHOICE:
                items = value if isinstance(value, (list, tuple, set)) else [value]
                if self.choices is not None:
                    issues.extend(
                        ValidationIssue("choice", f"{self.label}: {item!r} is not a valid option.")
                        for item in items
                        if str(item) not in self.choices
                    )
        return ValidationResult.of(issues)

    def _range_issues(self, number: float) -> list[ValidationIssue]:
        rules = self.validation
        issues: list[ValidationIssue] = []
        if rules.min_value is not None and number < rules.min_value:
            issues.append(
                ValidationIssue("min_value", f"{self.label} must be ≥ {rules.min_value}.")
            )
        if rules.max_value is not None and number > rules.max_value:
            issues.append(
                ValidationIssue("max_value", f"{self.label} must be ≤ {rules.max_value}.")
            )
        return issues

    def _text_issues(self, text: str) -> list[ValidationIssue]:
        rules = self.validation
        issues: list[ValidationIssue] = []
        if rules.min_length is not None and len(text) < rules.min_length:
            issues.append(ValidationIssue("min_length", f"{self.label} is too short."))
        if rules.max_length is not None and len(text) > rules.max_length:
            issues.append(ValidationIssue("max_length", f"{self.label} is too long."))
        if rules.pattern is not None and re.fullmatch(rules.pattern, text) is None:
            issues.append(ValidationIssue("pattern", f"{self.label} has an invalid format."))
        return issues
