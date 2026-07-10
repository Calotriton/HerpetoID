"""Shared GUI application state.

A single :class:`AppState` holds the currently open project and the application services, and emits
``project_changed`` when the open project changes so screens can react. This is how the presentation
layer is wired to the (Qt-free, already-tested) application services.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QObject, Signal

from herpetoid.application.catalog_service import CatalogService
from herpetoid.application.export import ExportService
from herpetoid.application.identification import IdentificationService
from herpetoid.application.project_service import ProjectContext, ProjectService
from herpetoid.application.registry import PluginRegistry
from herpetoid.application.settings import SettingsService
from herpetoid.application.statistics import StatisticsService
from herpetoid.infrastructure.exporters import default_exporters


class AppState(QObject):
    """The application's service hub and current-project holder."""

    project_changed = Signal()

    def __init__(
        self,
        *,
        registry: PluginRegistry,
        project_service: ProjectService,
        settings: SettingsService,
    ) -> None:
        super().__init__()
        self.registry = registry
        self.settings = settings
        # Session-wide defaults picked in the main-window toolbar; screens pre-select them on
        # refresh but keep their own combos as the actual inputs (no double source of truth).
        self.default_algorithm_id: str | None = None
        self.default_module_id: str | None = None
        self.identification = IdentificationService()
        self.statistics = StatisticsService()
        self.export = ExportService(default_exporters())
        self._project_service = project_service
        self._project: ProjectContext | None = None

    @property
    def project(self) -> ProjectContext | None:
        return self._project

    @property
    def catalog(self) -> CatalogService | None:
        return CatalogService(self._project) if self._project is not None else None

    def create_project(self, path: Path, name: str) -> None:
        self._set_project(self._project_service.create(path, name))

    def open_project(self, path: Path) -> None:
        self._set_project(self._project_service.open(path))

    def close_project(self) -> None:
        if self._project is not None:
            self._project.close()
            self._project = None
            self.project_changed.emit()

    def _set_project(self, context: ProjectContext) -> None:
        if self._project is not None:
            self._project.close()
        self._project = context
        self.settings.add_recent_project(str(context.path))
        self.project_changed.emit()
