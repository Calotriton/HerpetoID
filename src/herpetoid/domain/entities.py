"""Domain entities: the persistent photo-ID catalog model.

Pure dataclasses with identity (``id``) and lifecycle. They carry no persistence or GUI concerns; the
infrastructure layer maps them to SQLAlchemy rows via repositories. ``id`` is ``None`` until an entity
has been persisted (the store assigns it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from .enums import ImageAspect, IndividualStatus, MatchDecision, Sex
from .values import Location, PluginRef


@dataclass(slots=True)
class Project:
    """Self-metadata for a project bundle (one row per bundle)."""

    name: str
    uuid: str
    description: str = ""
    schema_version: int = 1
    app_version: str = ""
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class Species:
    """A species tracked within a project, handled by a species module."""

    scientific_name: str
    common_name: str = ""
    module: PluginRef | None = None
    id: int | None = None


@dataclass(slots=True)
class Individual:
    """A cataloged animal — the identity that observations are linked to."""

    species_id: int
    code: str  # catalog code / label
    name: str = ""
    sex: Sex = Sex.UNDETERMINED
    notes: str = ""
    status: IndividualStatus = IndividualStatus.ACTIVE
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(slots=True)
class Observation:
    """A single encounter: image(s) + metadata, optionally linked to an individual."""

    species_id: int
    observer: str = ""
    observed_at: date | datetime | None = None
    notes: str = ""
    location: Location = field(default_factory=Location)
    individual_id: int | None = None  # None => unidentified
    #: Dynamic species-specific field values (field key -> value), loaded from the metadata store.
    measurements: dict[str, Any] = field(default_factory=dict)
    id: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_identified(self) -> bool:
        return self.individual_id is not None


@dataclass(slots=True)
class Image:
    """One image belonging to an observation."""

    observation_id: int
    rel_path: str  # path relative to the project bundle root
    original_filename: str = ""
    file_hash: str = ""
    width: int = 0
    height: int = 0
    image_format: str = ""
    captured_at: datetime | None = None
    thumbnail_path: str | None = None
    aspect: ImageAspect = ImageAspect.UNKNOWN
    #: Quarter turns the researcher applied, clockwise degrees. The file on disk is never
    #: rewritten: the turn is applied on load, along with the ROI (see
    #: :mod:`herpetoid.application.orientation`).
    rotation: int = 0
    id: int | None = None


@dataclass(slots=True)
class DescriptorRecord:
    """Bookkeeping for a feature descriptor stored as a compressed ``.npz`` outside the database."""

    image_id: int
    algorithm: PluginRef
    rel_path: str  # bundle-relative path to the .npz
    descriptor_type: str = ""
    dtype: str = ""
    shape: tuple[int, ...] = ()
    # param_hash identifies the algorithm config used, so stale descriptors are detectable:
    param_hash: str = ""
    checksum: str = ""
    id: int | None = None
    created_at: datetime | None = None


@dataclass(slots=True)
class MatchRun:
    """One identification query execution (recorded for provenance)."""

    query_image_id: int
    algorithm: PluginRef  # or the fused pseudo-algorithm
    fusion_strategy: str | None = None
    created_at: datetime | None = None
    id: int | None = None


@dataclass(slots=True)
class Match:
    """A single ranked candidate within a match run, plus the human decision."""

    run_id: int
    rank: int
    score: float
    normalized_score: float
    candidate_individual_id: int | None = None
    candidate_image_id: int | None = None
    decision: MatchDecision = MatchDecision.PENDING
    decided_by: str | None = None
    decided_at: datetime | None = None
    id: int | None = None

    @property
    def is_decided(self) -> bool:
        return self.decision is not MatchDecision.PENDING
