"""SQLAlchemy 2.0 ORM models for a project-bundle database.

One SQLite database lives inside each portable project bundle. Feature descriptors are **not** stored
here -- only a bundle-relative path to the compressed ``.npz`` file (see :class:`DescriptorModel`).
Repositories map these rows to and from the persistence-agnostic domain entities.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

#: Bumped when the ORM schema changes in a way that needs a migration.
SCHEMA_VERSION = 1


class Base(DeclarativeBase):
    """Declarative base for all bundle models."""


class ProjectModel(Base):
    """Self-metadata for the bundle (a single row)."""

    __tablename__ = "project"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    uuid: Mapped[str] = mapped_column(String(36), unique=True)
    description: Mapped[str] = mapped_column(Text, default="")
    schema_version: Mapped[int] = mapped_column(default=SCHEMA_VERSION)
    app_version: Mapped[str] = mapped_column(String(50), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class SpeciesModuleModel(Base):
    """Provenance record of a species-module plugin used in this project."""

    __tablename__ = "species_modules"

    id: Mapped[int] = mapped_column(primary_key=True)
    module_id: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    version: Mapped[str] = mapped_column(String(50), default="")
    source: Mapped[str] = mapped_column(String(255), default="")


class AlgorithmModel(Base):
    """Provenance record of an algorithm plugin (id + version + config) used in this project."""

    __tablename__ = "algorithms"

    id: Mapped[int] = mapped_column(primary_key=True)
    algorithm_id: Mapped[str] = mapped_column(String(255), unique=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    version: Mapped[str] = mapped_column(String(50), default="")
    family: Mapped[str] = mapped_column(String(50), default="")
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SpeciesModel(Base):
    """A species tracked in the project."""

    __tablename__ = "species"

    id: Mapped[int] = mapped_column(primary_key=True)
    scientific_name: Mapped[str] = mapped_column(String(255), unique=True)
    common_name: Mapped[str] = mapped_column(String(255), default="")
    module_id: Mapped[str | None] = mapped_column(String(255))
    module_version: Mapped[str] = mapped_column(String(50), default="")

    individuals: Mapped[list[IndividualModel]] = relationship(
        back_populates="species", cascade="all, delete-orphan"
    )
    observations: Mapped[list[ObservationModel]] = relationship(back_populates="species")


class IndividualModel(Base):
    """A cataloged animal."""

    __tablename__ = "individuals"

    id: Mapped[int] = mapped_column(primary_key=True)
    species_id: Mapped[int] = mapped_column(ForeignKey("species.id"))
    code: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(255), default="")
    sex: Mapped[str] = mapped_column(String(20), default="undetermined")
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    species: Mapped[SpeciesModel] = relationship(back_populates="individuals")
    observations: Mapped[list[ObservationModel]] = relationship(back_populates="individual")

    __table_args__ = (UniqueConstraint("species_id", "code", name="uq_individual_code"),)


class ObservationModel(Base):
    """A single encounter (image(s) + metadata)."""

    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    species_id: Mapped[int] = mapped_column(ForeignKey("species.id"))
    individual_id: Mapped[int | None] = mapped_column(ForeignKey("individuals.id"))
    observer: Mapped[str] = mapped_column(String(255), default="")
    observed_at: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str] = mapped_column(Text, default="")
    location_lat: Mapped[float | None] = mapped_column(Float)
    location_lon: Mapped[float | None] = mapped_column(Float)
    location_accuracy: Mapped[float | None] = mapped_column(Float)
    location_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    species: Mapped[SpeciesModel] = relationship(back_populates="observations")
    individual: Mapped[IndividualModel | None] = relationship(back_populates="observations")
    images: Mapped[list[ImageModel]] = relationship(
        back_populates="observation", cascade="all, delete-orphan"
    )
    metadata_values: Mapped[list[MetadataModel]] = relationship(
        back_populates="observation", cascade="all, delete-orphan"
    )


class ImageModel(Base):
    """One image of an observation."""

    __tablename__ = "images"

    id: Mapped[int] = mapped_column(primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id"))
    rel_path: Mapped[str] = mapped_column(String(1024))
    original_filename: Mapped[str] = mapped_column(String(255), default="")
    file_hash: Mapped[str] = mapped_column(String(64), default="")
    width: Mapped[int] = mapped_column(default=0)
    height: Mapped[int] = mapped_column(default=0)
    image_format: Mapped[str] = mapped_column(String(16), default="")
    captured_at: Mapped[datetime | None] = mapped_column(DateTime)
    thumbnail_path: Mapped[str | None] = mapped_column(String(1024))
    aspect: Mapped[str] = mapped_column(String(20), default="unknown")

    observation: Mapped[ObservationModel] = relationship(back_populates="images")
    descriptors: Mapped[list[DescriptorModel]] = relationship(
        back_populates="image", cascade="all, delete-orphan"
    )


class DescriptorModel(Base):
    """Path + metadata for a feature descriptor stored as a compressed ``.npz`` outside SQLite."""

    __tablename__ = "descriptors"

    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id"))
    algorithm_id: Mapped[str] = mapped_column(String(255))
    algorithm_version: Mapped[str] = mapped_column(String(50), default="")
    rel_path: Mapped[str] = mapped_column(String(1024))
    descriptor_type: Mapped[str] = mapped_column(String(50), default="")
    dtype: Mapped[str] = mapped_column(String(50), default="")
    shape: Mapped[list[int]] = mapped_column(JSON, default=list)
    param_hash: Mapped[str] = mapped_column(String(64), default="")
    checksum: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    image: Mapped[ImageModel] = relationship(back_populates="descriptors")

    __table_args__ = (
        UniqueConstraint("image_id", "algorithm_id", "param_hash", name="uq_descriptor"),
    )


class ImageRoiModel(Base):
    """A region of interest marked on an image (used to crop the pattern region for matching)."""

    __tablename__ = "image_rois"

    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("images.id"), unique=True)
    kind: Mapped[str] = mapped_column(String(20), default="rectangle")
    points: Mapped[list[list[float]]] = mapped_column(JSON, default=list)


class FieldDefinitionModel(Base):
    """A declared observation field, persisted so a bundle is self-describing without the plugin."""

    __tablename__ = "field_definitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    species_id: Mapped[int | None] = mapped_column(ForeignKey("species.id"))
    field_key: Mapped[str] = mapped_column(String(100))
    label: Mapped[str] = mapped_column(String(255), default="")
    type: Mapped[str] = mapped_column(String(30), default="text")
    unit: Mapped[str | None] = mapped_column(String(30))
    field_group: Mapped[str] = mapped_column(String(30), default="general")
    required: Mapped[bool] = mapped_column(default=False)
    choices: Mapped[list[str]] = mapped_column(JSON, default=list)
    order: Mapped[int] = mapped_column(default=0)

    __table_args__ = (UniqueConstraint("species_id", "field_key", name="uq_field_definition"),)


class MetadataModel(Base):
    """A dynamic (typed EAV) observation field value."""

    __tablename__ = "metadata"

    id: Mapped[int] = mapped_column(primary_key=True)
    observation_id: Mapped[int] = mapped_column(ForeignKey("observations.id"))
    field_key: Mapped[str] = mapped_column(String(100))
    field_group: Mapped[str] = mapped_column(String(30), default="measurement")
    value_text: Mapped[str | None] = mapped_column(Text)
    value_number: Mapped[float | None] = mapped_column(Float)
    value_bool: Mapped[bool | None] = mapped_column()
    value_datetime: Mapped[datetime | None] = mapped_column(DateTime)
    unit: Mapped[str | None] = mapped_column(String(30))

    observation: Mapped[ObservationModel] = relationship(back_populates="metadata_values")

    __table_args__ = (UniqueConstraint("observation_id", "field_key", name="uq_metadata"),)


class MatchRunModel(Base):
    """One identification query execution."""

    __tablename__ = "match_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    query_image_id: Mapped[int] = mapped_column(ForeignKey("images.id"))
    algorithm_id: Mapped[str] = mapped_column(String(255), default="")
    fusion_strategy: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    matches: Mapped[list[MatchModel]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class MatchModel(Base):
    """A ranked candidate within a match run, plus the human decision."""

    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("match_runs.id"))
    rank: Mapped[int] = mapped_column()
    score: Mapped[float] = mapped_column(Float, default=0.0)
    normalized_score: Mapped[float] = mapped_column(Float, default=0.0)
    candidate_individual_id: Mapped[int | None] = mapped_column(ForeignKey("individuals.id"))
    candidate_image_id: Mapped[int | None] = mapped_column(ForeignKey("images.id"))
    decision: Mapped[str] = mapped_column(String(20), default="pending")
    decided_by: Mapped[str | None] = mapped_column(String(255))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)

    run: Mapped[MatchRunModel] = relationship(back_populates="matches")
