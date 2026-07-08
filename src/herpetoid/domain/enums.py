"""Domain enumerations for the photo-ID catalog model."""

from __future__ import annotations

from enum import StrEnum


class Sex(StrEnum):
    """An individual's determined sex (drives the sex-ratio statistic)."""

    MALE = "male"
    FEMALE = "female"
    UNDETERMINED = "undetermined"


class IndividualStatus(StrEnum):
    """Lifecycle state of a cataloged individual."""

    ACTIVE = "active"
    MERGED = "merged"  # merged into another individual (kept for provenance)
    ARCHIVED = "archived"


class MatchDecision(StrEnum):
    """The human decision on a candidate match (final call is always the user's)."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class ImageAspect(StrEnum):
    """Which side/aspect of the animal an image shows.

    Matters because, for many taxa, opposite sides carry different patterns and cannot be cross-matched.
    """

    UNKNOWN = "unknown"
    LEFT = "left"
    RIGHT = "right"
    DORSAL = "dorsal"
    VENTRAL = "ventral"
