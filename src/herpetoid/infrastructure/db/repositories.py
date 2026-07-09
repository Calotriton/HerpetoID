"""Repositories: translate between ORM rows and persistence-agnostic domain entities.

Each repository takes an active :class:`~sqlalchemy.orm.Session`; transaction scope is owned by the
caller (typically ``with database.session() as session: ...``).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from herpetoid.api import ROI, ROIKind
from herpetoid.domain import (
    Image,
    ImageAspect,
    Individual,
    IndividualStatus,
    Location,
    Observation,
    PluginRef,
    Project,
    Sex,
    Species,
)

from .models import (
    ImageModel,
    ImageRoiModel,
    IndividualModel,
    MetadataModel,
    ObservationModel,
    ProjectModel,
    SpeciesModel,
)


# ---------------------------------------------------------------------------------------------------
# Mapping helpers
# ---------------------------------------------------------------------------------------------------
def _as_datetime(value: date | datetime | None) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime(value.year, value.month, value.day)


def _metadata_value(row: MetadataModel) -> Any:
    if row.value_number is not None:
        return row.value_number
    if row.value_bool is not None:
        return row.value_bool
    if row.value_datetime is not None:
        return row.value_datetime
    return row.value_text


def _assign_metadata_value(row: MetadataModel, value: Any) -> None:
    row.value_text = row.value_number = row.value_bool = row.value_datetime = None
    if isinstance(value, bool):
        row.value_bool = value
    elif isinstance(value, (int, float)):
        row.value_number = float(value)
    elif isinstance(value, datetime):
        row.value_datetime = value
    else:
        row.value_text = str(value)


def _project_to_entity(model: ProjectModel) -> Project:
    return Project(
        name=model.name,
        uuid=model.uuid,
        description=model.description,
        schema_version=model.schema_version,
        app_version=model.app_version,
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _species_to_entity(model: SpeciesModel) -> Species:
    module = PluginRef(model.module_id, model.module_version) if model.module_id else None
    return Species(
        scientific_name=model.scientific_name,
        common_name=model.common_name,
        module=module,
        id=model.id,
    )


def _individual_to_entity(model: IndividualModel) -> Individual:
    return Individual(
        species_id=model.species_id,
        code=model.code,
        name=model.name,
        sex=Sex(model.sex),
        notes=model.notes,
        status=IndividualStatus(model.status),
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


def _image_to_entity(model: ImageModel) -> Image:
    return Image(
        observation_id=model.observation_id,
        rel_path=model.rel_path,
        original_filename=model.original_filename,
        file_hash=model.file_hash,
        width=model.width,
        height=model.height,
        image_format=model.image_format,
        captured_at=model.captured_at,
        thumbnail_path=model.thumbnail_path,
        aspect=ImageAspect(model.aspect),
        id=model.id,
    )


def _observation_to_entity(model: ObservationModel) -> Observation:
    measurements = {row.field_key: _metadata_value(row) for row in model.metadata_values}
    return Observation(
        species_id=model.species_id,
        observer=model.observer,
        observed_at=model.observed_at,
        notes=model.notes,
        location=Location(
            latitude=model.location_lat,
            longitude=model.location_lon,
            accuracy_m=model.location_accuracy,
            name=model.location_name,
        ),
        individual_id=model.individual_id,
        measurements=measurements,
        id=model.id,
        created_at=model.created_at,
        updated_at=model.updated_at,
    )


# ---------------------------------------------------------------------------------------------------
# Repositories
# ---------------------------------------------------------------------------------------------------
class ProjectRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, project: Project) -> Project:
        model = ProjectModel(
            name=project.name,
            uuid=project.uuid,
            description=project.description,
            schema_version=project.schema_version,
            app_version=project.app_version,
        )
        self._session.add(model)
        self._session.flush()
        project.id = model.id
        return project

    def get(self) -> Project | None:
        model = self._session.scalars(select(ProjectModel)).first()
        return _project_to_entity(model) if model is not None else None


class SpeciesRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, species: Species) -> Species:
        model = SpeciesModel(
            scientific_name=species.scientific_name,
            common_name=species.common_name,
            module_id=species.module.plugin_id if species.module else None,
            module_version=species.module.version if species.module else "",
        )
        self._session.add(model)
        self._session.flush()
        species.id = model.id
        return species

    def get(self, species_id: int) -> Species | None:
        model = self._session.get(SpeciesModel, species_id)
        return _species_to_entity(model) if model is not None else None

    def get_by_name(self, scientific_name: str) -> Species | None:
        stmt = select(SpeciesModel).where(SpeciesModel.scientific_name == scientific_name)
        model = self._session.scalars(stmt).first()
        return _species_to_entity(model) if model is not None else None

    def list(self) -> list[Species]:
        stmt = select(SpeciesModel).order_by(SpeciesModel.scientific_name)
        return [_species_to_entity(model) for model in self._session.scalars(stmt)]


class IndividualRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, individual: Individual) -> Individual:
        model = IndividualModel(
            species_id=individual.species_id,
            code=individual.code,
            name=individual.name,
            sex=individual.sex.value,
            notes=individual.notes,
            status=individual.status.value,
        )
        self._session.add(model)
        self._session.flush()
        individual.id = model.id
        return individual

    def get(self, individual_id: int) -> Individual | None:
        model = self._session.get(IndividualModel, individual_id)
        return _individual_to_entity(model) if model is not None else None

    def list_for_species(self, species_id: int) -> list[Individual]:
        stmt = (
            select(IndividualModel)
            .where(IndividualModel.species_id == species_id)
            .order_by(IndividualModel.code)
        )
        return [_individual_to_entity(model) for model in self._session.scalars(stmt)]

    def get_by_code(self, species_id: int, code: str) -> Individual | None:
        stmt = select(IndividualModel).where(
            IndividualModel.species_id == species_id, IndividualModel.code == code
        )
        model = self._session.scalars(stmt).first()
        return _individual_to_entity(model) if model is not None else None

    def list_all(self) -> list[Individual]:
        stmt = select(IndividualModel).order_by(IndividualModel.code)
        return [_individual_to_entity(model) for model in self._session.scalars(stmt)]

    def update(self, individual: Individual) -> None:
        if individual.id is None:
            raise ValueError("cannot update an individual without an id")
        model = self._session.get(IndividualModel, individual.id)
        if model is None:
            raise KeyError(f"no individual with id {individual.id}")
        model.code = individual.code
        model.name = individual.name
        model.sex = individual.sex.value
        model.notes = individual.notes
        model.status = individual.status.value

    def count(self) -> int:
        return int(self._session.scalar(select(func.count()).select_from(IndividualModel)) or 0)


class ImageRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, image: Image) -> Image:
        model = ImageModel(
            observation_id=image.observation_id,
            rel_path=image.rel_path,
            original_filename=image.original_filename,
            file_hash=image.file_hash,
            width=image.width,
            height=image.height,
            image_format=image.image_format,
            captured_at=image.captured_at,
            thumbnail_path=image.thumbnail_path,
            aspect=image.aspect.value,
        )
        self._session.add(model)
        self._session.flush()
        image.id = model.id
        return image

    def list_for_observation(self, observation_id: int) -> list[Image]:
        stmt = select(ImageModel).where(ImageModel.observation_id == observation_id)
        return [_image_to_entity(model) for model in self._session.scalars(stmt)]

    def list_all(self) -> list[Image]:
        stmt = select(ImageModel).order_by(ImageModel.id)
        return [_image_to_entity(model) for model in self._session.scalars(stmt)]

    def get_roi(self, image_id: int) -> ROI | None:
        model = self._session.scalars(
            select(ImageRoiModel).where(ImageRoiModel.image_id == image_id)
        ).first()
        if model is None:
            return None
        points = tuple((float(p[0]), float(p[1])) for p in model.points)
        return ROI(kind=ROIKind(model.kind), points=points)

    def set_roi(self, image_id: int, roi: ROI) -> None:
        points = [[float(x), float(y)] for x, y in roi.points]
        model = self._session.scalars(
            select(ImageRoiModel).where(ImageRoiModel.image_id == image_id)
        ).first()
        if model is None:
            self._session.add(ImageRoiModel(image_id=image_id, kind=str(roi.kind), points=points))
        else:
            model.kind = str(roi.kind)
            model.points = points


class ObservationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, observation: Observation) -> Observation:
        model = ObservationModel(
            species_id=observation.species_id,
            individual_id=observation.individual_id,
            observer=observation.observer,
            observed_at=_as_datetime(observation.observed_at),
            notes=observation.notes,
            location_lat=observation.location.latitude,
            location_lon=observation.location.longitude,
            location_accuracy=observation.location.accuracy_m,
            location_name=observation.location.name,
        )
        for key, value in observation.measurements.items():
            row = MetadataModel(field_key=key)
            _assign_metadata_value(row, value)
            model.metadata_values.append(row)
        self._session.add(model)
        self._session.flush()
        observation.id = model.id
        return observation

    def get(self, observation_id: int) -> Observation | None:
        model = self._session.get(ObservationModel, observation_id)
        return _observation_to_entity(model) if model is not None else None

    def list_for_individual(self, individual_id: int) -> list[Observation]:
        stmt = (
            select(ObservationModel)
            .where(ObservationModel.individual_id == individual_id)
            .order_by(ObservationModel.observed_at)
        )
        return [_observation_to_entity(model) for model in self._session.scalars(stmt)]

    def link_to_individual(self, observation_id: int, individual_id: int | None) -> None:
        model = self._session.get(ObservationModel, observation_id)
        if model is None:
            raise KeyError(f"no observation with id {observation_id}")
        model.individual_id = individual_id

    def update(self, observation: Observation) -> None:
        if observation.id is None:
            raise ValueError("cannot update an observation without an id")
        model = self._session.get(ObservationModel, observation.id)
        if model is None:
            raise KeyError(f"no observation with id {observation.id}")
        model.observer = observation.observer
        model.observed_at = _as_datetime(observation.observed_at)
        model.notes = observation.notes
        model.individual_id = observation.individual_id
        model.location_lat = observation.location.latitude
        model.location_lon = observation.location.longitude
        model.location_accuracy = observation.location.accuracy_m
        model.location_name = observation.location.name
        model.metadata_values.clear()  # cascade delete-orphan marks the old rows for deletion
        # Flush the orphan deletes before inserting the replacements: otherwise SQLAlchemy may INSERT a
        # new (observation_id, field_key) row before DELETEing the old one, tripping the UNIQUE index.
        self._session.flush()
        for key, value in observation.measurements.items():
            row = MetadataModel(field_key=key)
            _assign_metadata_value(row, value)
            model.metadata_values.append(row)

    def delete(self, observation_id: int) -> None:
        """Delete an observation and (via cascade) its images and metadata values."""
        model = self._session.get(ObservationModel, observation_id)
        if model is not None:
            self._session.delete(model)

    def list_all(self) -> list[Observation]:
        stmt = select(ObservationModel).order_by(ObservationModel.observed_at)
        return [_observation_to_entity(model) for model in self._session.scalars(stmt)]

    def list_for_species(self, species_id: int) -> list[Observation]:
        stmt = (
            select(ObservationModel)
            .where(ObservationModel.species_id == species_id)
            .order_by(ObservationModel.id)
        )
        return [_observation_to_entity(model) for model in self._session.scalars(stmt)]

    def count(self) -> int:
        return int(self._session.scalar(select(func.count()).select_from(ObservationModel)) or 0)
