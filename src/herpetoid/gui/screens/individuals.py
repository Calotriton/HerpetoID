"""Individual Browser: the catalog of identified individuals, with a preview image."""

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

from herpetoid.domain import Individual
from herpetoid.gui.state import AppState
from herpetoid.gui.widgets.image_viewer import ImageViewer

_COLUMNS = ["Code", "Sex", "Status", "Observations"]


class IndividualBrowserScreen(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._individuals: list[Individual] = []

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
        splitter.setSizes([500, 560])
        layout.addWidget(splitter)

        state.project_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        catalog = self._state.catalog
        self.viewer.clear()
        if catalog is None:
            self._individuals = []
            self.table.setRowCount(0)
            return
        self._individuals = catalog.list_individuals()
        self.table.setRowCount(len(self._individuals))
        for row, individual in enumerate(self._individuals):
            count = (
                len(catalog.observations_for_individual(individual.id))
                if individual.id is not None
                else 0
            )
            cells = [individual.code, str(individual.sex), str(individual.status), str(count)]
            for column, text in enumerate(cells):
                self.table.setItem(row, column, QTableWidgetItem(text))
        if self._individuals:
            self.table.selectRow(0)

    def _on_select(self) -> None:
        project = self._state.project
        catalog = self._state.catalog
        row = self.table.currentRow()
        if project is None or catalog is None or not 0 <= row < len(self._individuals):
            return
        individual = self._individuals[row]
        if individual.id is None:
            return
        for observation in catalog.observations_for_individual(individual.id):
            if observation.id is None:
                continue
            images = catalog.images_for(observation.id)
            if images:
                try:
                    self.viewer.set_image(project.image_store.load(images[0].rel_path))
                    return
                except (OSError, ValueError):
                    pass
        self.viewer.clear()
