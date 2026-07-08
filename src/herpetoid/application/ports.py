"""Application-layer ports (interfaces the infrastructure/presentation layers implement)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TypeVar

import numpy as np

T = TypeVar("T")


class TaskRunner(Protocol):
    """Runs a unit of work, optionally off the UI thread.

    The default :class:`SynchronousTaskRunner` runs inline; the GUI provides a ``QThreadPool``-backed
    implementation that keeps the interface responsive during long operations (import, feature
    extraction, matching, export) and marshals the callback back to the UI thread.
    """

    def submit(
        self, func: Callable[[], T], *, on_done: Callable[[T], None] | None = None
    ) -> None: ...


class SynchronousTaskRunner:
    """A :class:`TaskRunner` that runs work inline (used in tests and headless contexts)."""

    def submit(self, func: Callable[[], T], *, on_done: Callable[[T], None] | None = None) -> None:
        result = func()
        if on_done is not None:
            on_done(result)


class ImageStore(Protocol):
    """Loads and stores image files within a project bundle (paths are bundle-relative)."""

    def load(self, rel_path: str) -> np.ndarray: ...

    def save(self, source: Path, rel_path: str) -> None: ...
