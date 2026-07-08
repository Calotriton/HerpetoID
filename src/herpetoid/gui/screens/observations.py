"""Observations browser: a table of observations with the selected one's image in a zoom/pan viewer."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHeaderView,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from herpetoid.domain import Observation
from herpetoid.gui.state import AppState
from herpetoid.gui.widgets.image_viewer import ImageViewer

_COLUMNS = ["ID", "Species", "Observer", "Date", "Measurements"]


class ObservationsScreen(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._observations: list[Observation] = []
        self._species_names: dict[int | None, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_select)

        self.viewer = ImageViewer()

        splitter.addWidget(self.table)
        splitter.addWidget(self.viewer)
        splitter.setSizes([560, 560])
        layout.addWidget(splitter)

        state.project_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        catalog = self._state.catalog
        self.viewer.clear()
        if catalog is None:
            self._observations = []
            self.table.setRowCount(0)
            return
        self._species_names = {s.id: s.scientific_name for s in catalog.list_species()}
        self._observations = catalog.list_observations()
        self.table.setRowCount(len(self._observations))
        for row, obs in enumerate(self._observations):
            date_text = obs.observed_at.isoformat()[:10] if obs.observed_at is not None else ""
            measurements = ", ".join(f"{k}={v}" for k, v in obs.measurements.items())
            cells = [
                str(obs.id),
                self._species_names.get(obs.species_id, ""),
                obs.observer,
                date_text,
                measurements,
            ]
            for column, text in enumerate(cells):
                self.table.setItem(row, column, QTableWidgetItem(text))
        if self._observations:
            self.table.selectRow(0)  # show the first observation's image right away

    def _on_select(self) -> None:
        project = self._state.project
        catalog = self._state.catalog
        row = self.table.currentRow()
        if project is None or catalog is None or not 0 <= row < len(self._observations):
            return
        observation = self._observations[row]
        images = catalog.images_for(observation.id) if observation.id is not None else []
        if not images:
            self.viewer.clear()
            return
        try:
            self.viewer.set_image(project.image_store.load(images[0].rel_path))
        except (OSError, ValueError):
            self.viewer.clear()
