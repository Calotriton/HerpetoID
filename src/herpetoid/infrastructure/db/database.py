"""Per-bundle SQLite database: engine, session factory and schema creation.

Each portable project bundle has its own SQLite file. Foreign-key enforcement (off by default in
SQLite) is enabled on every connection so cascade deletes and referential integrity behave correctly.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Database:
    """Owns the SQLAlchemy engine and session factory for one project-bundle database."""

    def __init__(self, url: str) -> None:
        self._engine = create_engine(url)
        event.listen(self._engine, "connect", _enable_sqlite_foreign_keys)
        self._session_factory = sessionmaker(bind=self._engine, expire_on_commit=False)

    @classmethod
    def in_memory(cls) -> Database:
        """An ephemeral in-memory database (used by tests)."""
        return cls("sqlite:///:memory:")

    @classmethod
    def at_path(cls, path: Path) -> Database:
        """A file-backed database at ``path`` (parent directories are created)."""
        path.parent.mkdir(parents=True, exist_ok=True)
        return cls(f"sqlite:///{path.as_posix()}")

    @property
    def engine(self) -> Engine:
        return self._engine

    def create_schema(self) -> None:
        """Create all tables (used when initializing a fresh bundle)."""
        Base.metadata.create_all(self._engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """A transactional session scope: commit on success, roll back on error, always close."""
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def dispose(self) -> None:
        self._engine.dispose()
