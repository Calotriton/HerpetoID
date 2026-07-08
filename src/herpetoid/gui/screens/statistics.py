"""Statistics screen: project counts + field-driven statistics, plus data/PDF exports."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from herpetoid.api import DerivedStatistic
from herpetoid.application.catalog_service import CatalogService
from herpetoid.application.export import ExportData
from herpetoid.gui.state import AppState
from herpetoid.infrastructure.pdf_export import PdfExporter

_EXPORTS = (("CSV", "csv"), ("Excel", "xlsx"), ("JSON", "json"), ("PDF", "pdf"))
_FILTERS = {
    "csv": "CSV (*.csv)",
    "xlsx": "Excel (*.xlsx)",
    "json": "JSON (*.json)",
    "pdf": "PDF (*.pdf)",
}


class StatisticsScreen(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)

        header = QHBoxLayout()
        header.addWidget(QLabel("<b>Project statistics</b>"))
        header.addStretch(1)
        refresh_button = QPushButton("Refresh")
        refresh_button.clicked.connect(self._refresh)
        header.addWidget(refresh_button)
        for label, fmt in _EXPORTS:
            button = QPushButton(f"Export {label}")
            button.clicked.connect(lambda _checked=False, f=fmt: self._export(f))
            header.addWidget(button)
        layout.addLayout(header)

        self.summary_label = QLabel()
        layout.addWidget(self.summary_label)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["Statistic", "Value"])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, 1)

        state.project_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        catalog = self._state.catalog
        if catalog is None:
            self.summary_label.setText("No project open.")
            self.table.setRowCount(0)
            return

        observations = catalog.list_observations()
        individuals = catalog.list_individuals()
        report = self._state.statistics.compute(
            individuals=individuals,
            observations=observations,
            derived=self._collect_derived(catalog),
        )

        dates = ""
        if report.first_observation is not None and report.last_observation is not None:
            dates = (
                f"  ·  Dates: {report.first_observation.date()} - {report.last_observation.date()}"
            )
        self.summary_label.setText(
            f"Individuals: {report.individual_count}  ·  Observations: {report.observation_count}"
            f"  ·  Recaptures: {report.recapture_count}{dates}"
        )

        rows: list[tuple[str, str]] = []
        for key, value in report.aggregates.items():
            rows.append((key, f"{value:.4g}"))
        for key, distribution in report.distributions.items():
            rows.append((key, ", ".join(f"{k}: {v}" for k, v in distribution.items())))
        for key, points in report.growth.items():
            rows.append((key, f"{len(points)} points"))
        self._fill_table(rows)

    def _collect_derived(self, catalog: CatalogService) -> list[DerivedStatistic]:
        specs: list[DerivedStatistic] = []
        seen: set[str] = set()
        for species in catalog.list_species():
            if (
                species.module is None
                or self._state.registry.module(species.module.plugin_id) is None
            ):
                continue
            try:
                module = self._state.registry.create_module(species.module.plugin_id)
                profile = module.define_species_profile()
            except Exception:  # a broken module must not break the dashboard
                continue
            for spec in profile.derived_statistics:
                if spec.key not in seen:
                    seen.add(spec.key)
                    specs.append(spec)
        return specs

    def _fill_table(self, rows: list[tuple[str, str]]) -> None:
        self.table.setRowCount(len(rows))
        for row_index, (name, value) in enumerate(rows):
            self.table.setItem(row_index, 0, QTableWidgetItem(name))
            self.table.setItem(row_index, 1, QTableWidgetItem(value))

    # -- exports --------------------------------------------------------------------------------
    def build_export_data(self) -> ExportData | None:
        catalog = self._state.catalog
        project = self._state.project
        if catalog is None or project is None:
            return None
        return ExportData(
            project=project.project,
            species=catalog.list_species(),
            individuals=catalog.list_individuals(),
            observations=catalog.list_observations(),
            images=catalog.list_images(),
        )

    def export_to(self, format_id: str, destination: Path) -> None:
        data = self.build_export_data()
        if data is None:
            return
        if format_id == "pdf":
            project = self._state.project
            PdfExporter(
                bundle_root=project.path if project else None,
                title=f"HerpetoID - {data.project.name}",
            ).export(data, destination)
        else:
            self._state.export.export(format_id, data, destination)

    def _export(self, format_id: str) -> None:
        if self._state.catalog is None:
            return
        destination, _ = QFileDialog.getSaveFileName(
            self, f"Export {format_id.upper()}", f"export.{format_id}", _FILTERS[format_id]
        )
        if not destination:
            return
        try:
            self.export_to(format_id, Path(destination))
        except Exception as exc:  # surface export errors without crashing
            self.summary_label.setText(f"Export failed: {exc}")
            return
        self.summary_label.setText(f"Exported to {destination}")
