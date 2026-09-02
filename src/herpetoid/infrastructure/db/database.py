"""Per-bundle SQLite database: engine, session factory and schema creation.

Each portable project bundle has its own SQLite file. Foreign-key enforcement (off by default in
SQLite) is enabled on every connection so cascade deletes and referential integrity behave correctly.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from .models import Base


def _enable_sqlite_foreign_keys(dbapi_connection: Any, _record: Any) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _add_column_clause(column: Any, engine: Engine) -> str | None:
    """The ``ADD COLUMN`` clause for a missing column, or ``None`` if it cannot be added safely.

    SQLite refuses ``NOT NULL`` without a default on an existing table -- rightly, since it cannot
    know what the existing rows should hold. Such a column is left alone rather than guessed at.
    """
    default = getattr(column.server_default, "arg", None)
    literal = None if default is None else str(getattr(default, "text", default))
    if not column.nullable and literal is None:
        return None
    clause = f'"{column.name}" {column.type.compile(engine.dialect)}'
    if literal is not None:
        clause += f" DEFAULT {literal}"
    if not column.nullable:
        clause += " NOT NULL"
    return clause

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

    def migrate_schema(self) -> list[str]:
        """Add columns the models declare that an older bundle's tables lack.

        A bundle is a portable folder that outlives the version of HerpetoID that wrote it, and
        ``create_all`` only adds missing *tables*. This adds missing *columns*, which is what a
        researcher's existing project needs when a release records something new about an image
        or an observation. Purely additive: nothing is dropped, renamed or retyped, and a
        column is only added when its declaration says what existing rows should hold
        (nullable, or carrying a server default). Returns the ``table.column`` names added.
        """
        inspector = inspect(self._engine)
        added: list[str] = []
        with self._engine.begin() as connection:
            for table in Base.metadata.sorted_tables:
                if not inspector.has_table(table.name):
                    continue  # create_schema will make it in full
                present = {column['name'] for column in inspector.get_columns(table.name)}
                for column in table.columns:
                    if column.name in present:
                        continue
                    clause = _add_column_clause(column, self._engine)
                    if clause is None:
                        continue
                    connection.execute(
                        text(f'ALTER TABLE "{table.name}" ADD COLUMN {clause}')
                    )
                    added.append(f"{table.name}.{column.name}")
        return added

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
