"""Tests for declarative observation fields and their validation."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from herpetoid import api


def test_float_field_valid_and_range() -> None:
    field = api.FieldDefinition(
        "svl",
        "SVL",
        api.FieldType.FLOAT,
        unit="mm",
        validation=api.Validation(required=True, min_value=0.0),
    )
    assert field.validate_value(12.3).ok
    below = field.validate_value(-1.0)
    assert not below.ok
    assert below.errors[0].code == "min_value"
    assert not field.validate_value(None).ok  # required
    assert not field.validate_value("abc").ok  # wrong type


def test_integer_rejects_bool_and_non_integer() -> None:
    field = api.FieldDefinition("n", "N", api.FieldType.INTEGER)
    assert field.validate_value(3).ok
    assert not field.validate_value(3.5).ok
    assert not field.validate_value(True).ok  # bool is not a valid integer value


def test_choice_field() -> None:
    field = api.FieldDefinition(
        "sex", "Sex", api.FieldType.CHOICE, choices=("male", "female", "undetermined")
    )
    assert field.validate_value("male").ok
    assert not field.validate_value("banana").ok


def test_choice_without_choices_raises() -> None:
    with pytest.raises(ValueError):
        api.FieldDefinition("x", "X", api.FieldType.CHOICE)


def test_text_pattern_and_length() -> None:
    field = api.FieldDefinition(
        "code",
        "Code",
        api.FieldType.TEXT,
        validation=api.Validation(pattern=r"[A-Z]{2}\d{2}", max_length=4),
    )
    assert field.validate_value("AB12").ok
    assert not field.validate_value("ab12").ok  # pattern
    assert not field.validate_value("ABC123").ok  # pattern + length


@given(value=st.floats(min_value=0.0, max_value=100.0, allow_nan=False))
def test_property_in_range_is_valid(value: float) -> None:
    field = api.FieldDefinition(
        "m", "M", api.FieldType.FLOAT, validation=api.Validation(min_value=0.0, max_value=100.0)
    )
    assert field.validate_value(value).ok


@given(value=st.floats(allow_nan=False, allow_infinity=False))
def test_property_validity_matches_range(value: float) -> None:
    field = api.FieldDefinition(
        "m", "M", api.FieldType.FLOAT, validation=api.Validation(min_value=0.0, max_value=100.0)
    )
    assert field.validate_value(value).ok == (0.0 <= value <= 100.0)
