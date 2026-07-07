"""Validation result value objects returned by :meth:`SpeciesModule.validate_image` and by field
validation. Pure and Qt-free.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .enums import Severity


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A single validation problem, with a machine-readable code and human message."""

    code: str
    message: str
    severity: Severity = Severity.ERROR


@dataclass(frozen=True, slots=True)
class ValidationResult:
    """Outcome of a validation. ``ok`` is derived: valid iff there are no error-severity issues."""

    issues: tuple[ValidationIssue, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(issue.severity is Severity.ERROR for issue in self.issues)

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.WARNING)

    @classmethod
    def success(cls) -> ValidationResult:
        """A passing result with no issues."""
        return cls(())

    @classmethod
    def of(cls, issues: Iterable[ValidationIssue]) -> ValidationResult:
        """Build a result from an iterable of issues (``ok`` computed from their severities)."""
        return cls(tuple(issues))

    def merge(self, other: ValidationResult) -> ValidationResult:
        """Combine two results, concatenating their issues."""
        return ValidationResult(self.issues + other.issues)
