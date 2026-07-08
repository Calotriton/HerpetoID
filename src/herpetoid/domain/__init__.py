"""Domain layer: entities, value objects and invariants for the photo-ID catalog.

Pure Python — no Qt, no SQLAlchemy. This is the stable core the application layer is written against.
"""

from __future__ import annotations

from .entities import (
    DescriptorRecord,
    Image,
    Individual,
    Match,
    MatchRun,
    Observation,
    Project,
    Species,
)
from .enums import ImageAspect, IndividualStatus, MatchDecision, Sex
from .values import Location, PluginRef

__all__ = [
    "DescriptorRecord",
    "Image",
    "ImageAspect",
    "Individual",
    "IndividualStatus",
    "Location",
    "Match",
    "MatchDecision",
    "MatchRun",
    "Observation",
    "PluginRef",
    "Project",
    "Sex",
    "Species",
]
