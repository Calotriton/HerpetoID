"""Project bundle lifecycle: create and open portable project bundles.

A bundle is a self-contained folder::

    MyStudy/
      project.db        SQLite database (individuals, observations, metadata, ...)
      images/           original observation images
      thumbnails/       generated thumbnails
      descriptors/      computed feature files (.npz)
      README.txt        auto-generated, so a shared bundle explains itself

This service is the composition point that wires the concrete database and image store for an open
project; higher-level services operate on the returned :class:`ProjectContext`.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from herpetoid.domain import Project
from herpetoid.infrastructure.db import SCHEMA_VERSION, Database
from herpetoid.infrastructure.db.repositories import ProjectRepository
from herpetoid.infrastructure.image_store import FileImageStore

_SUBDIRECTORIES = ("images", "thumbnails", "descriptors")
_DB_FILENAME = "project.db"


@dataclass(slots=True)
class ProjectContext:
    """A handle to an open project bundle."""

    path: Path
    project: Project
    database: Database
    image_store: FileImageStore

    def close(self) -> None:
        self.database.dispose()


class ProjectService:
    """Creates and opens project bundles."""

    def __init__(self, app_version: str = "") -> None:
        self._app_version = app_version

    def create(self, path: Path, name: str, *, description: str = "") -> ProjectContext:
        if path.exists() and any(path.iterdir()):
            raise FileExistsError(f"{path} already exists and is not empty")
        for subdirectory in _SUBDIRECTORIES:
            (path / subdirectory).mkdir(parents=True, exist_ok=True)

        database = Database.at_path(path / _DB_FILENAME)
        database.create_schema()
        with database.session() as session:
            ProjectRepository(session).add(
                Project(
                    name=name,
                    uuid=str(uuid4()),
                    description=description,
                    app_version=self._app_version,
                )
            )
        with database.session() as session:
            project = ProjectRepository(session).get()
        if project is None:
            raise RuntimeError("failed to persist the project record")

        self._write_readme(path, project)
        return ProjectContext(
            path=path, project=project, database=database, image_store=FileImageStore(path)
        )

    @staticmethod
    def is_project_bundle(path: Path) -> bool:
        """True if ``path`` looks like a HerpetoID bundle (contains the project database)."""
        return (path / _DB_FILENAME).exists()

    def open(self, path: Path) -> ProjectContext:
        db_path = path / _DB_FILENAME
        if not db_path.exists():
            raise FileNotFoundError(f"no HerpetoID project database at {db_path}")
        database = Database.at_path(db_path)
        database.create_schema()  # idempotent: adds any new tables to bundles from older versions
        database.migrate_schema()  # ...and any new columns those bundles' tables are missing
        with database.session() as session:
            project = ProjectRepository(session).get()
        if project is None:
            raise ValueError(f"{path} is not a valid HerpetoID project (empty database)")
        if project.schema_version > SCHEMA_VERSION:
            raise ValueError(
                f"project schema v{project.schema_version} is newer than supported v{SCHEMA_VERSION}"
            )
        return ProjectContext(
            path=path, project=project, database=database, image_store=FileImageStore(path)
        )

    @staticmethod
    def _write_readme(path: Path, project: Project) -> None:
        text = (
            "HerpetoID project bundle\n"
            "========================\n\n"
            f"Project: {project.name}\n"
            f"UUID: {project.uuid}\n\n"
            "This folder is a HerpetoID project. Open it in the HerpetoID application\n"
            "(File > Open Project) and select this folder.\n\n"
            "Contents:\n"
            "  project.db    - the project database (individuals, observations, metadata)\n"
            "  images/       - observation images\n"
            "  thumbnails/   - image thumbnails\n"
            "  descriptors/  - computed feature files (.npz)\n"
        )
        (path / "README.txt").write_text(text, encoding="utf-8")
