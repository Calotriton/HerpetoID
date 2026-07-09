"""Individual Browser: the catalog of identified individuals, with a preview image + info panel.

Each row has an *Edit* button to change the individual's code, name, sex, status, notes and the
species' declared measurements. The right panel shows the selected individual's picture above a
species-driven table of its details.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from herpetoid.api import FieldDefinition
from herpetoid.domain import Individual, IndividualStatus, Observation, Sex
from herpetoid.gui.state import AppState
from herpetoid.gui.widgets.dynamic_form import DynamicForm
from herpetoid.gui.widgets.image_viewer import ImageViewer
from herpetoid.gui.widgets.info_table import (
    InfoTable,
    format_date,
    observation_info_rows,
    species_field_definitions,
)
from herpetoid.gui.widgets.roi_preview import RoiPreview

_COLUMNS = ["Code", "Name", "Sex", "Status", "Obs.", ""]


class IndividualEditDialog(QDialog):
    """Edit an individual's identity fields plus the species' declared measurements."""

    def __init__(
        self,
        individual: Individual,
        fields: list[FieldDefinition],
        measurements: dict[str, Any],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Edit individual {individual.code}")
        self.setMinimumWidth(360)
        self._individual = individual

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.code_edit = QLineEdit(individual.code)
        form.addRow("Code", self.code_edit)
        self.name_edit = QLineEdit(individual.name)
        form.addRow("Name", self.name_edit)
        self.sex_combo = QComboBox()
        self.sex_combo.addItems([s.value for s in Sex])
        self.sex_combo.setCurrentText(individual.sex.value)
        form.addRow("Sex", self.sex_combo)
        self.status_combo = QComboBox()
        self.status_combo.addItems([s.value for s in IndividualStatus])
        self.status_combo.setCurrentText(individual.status.value)
        form.addRow("Status", self.status_combo)
        self.notes_edit = QLineEdit(individual.notes)
        form.addRow("Notes", self.notes_edit)
        layout.addLayout(form)

        self._form: DynamicForm | None = None
        if fields:
            layout.addWidget(QLabel("<b>Measurements</b>"))
            self._form = DynamicForm(fields)
            self._form.set_values(measurements)
            layout.addWidget(self._form)
            if not measurements:
                hint = QLabel("Saved to this individual's first observation.")
                hint.setStyleSheet("color: palette(mid); font-size: 11px;")
                layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def updated_individual(self) -> Individual:
        self._individual.code = self.code_edit.text().strip() or self._individual.code
        self._individual.name = self.name_edit.text().strip()
        self._individual.sex = Sex(self.sex_combo.currentText())
        self._individual.status = IndividualStatus(self.status_combo.currentText())
        self._individual.notes = self.notes_edit.text().strip()
        return self._individual

    def measurement_values(self) -> dict[str, Any]:
        if self._form is None:
            return {}
        return {k: v for k, v in self._form.values().items() if v is not None}


class IndividualBrowserScreen(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._individuals: list[Individual] = []
        self._individual_observations: list[Observation] = []
        self._obs_index = 0

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        header = self.table.horizontalHeader()
        # All columns get a bounded width (Interactive = user-resizable, but seeded here) with elision,
        # so no cell can balloon and push the Edit button off-screen / behind a horizontal scrollbar.
        for column in range(len(_COLUMNS) - 1):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(len(_COLUMNS) - 1, QHeaderView.ResizeMode.Fixed)  # Edit
        for column, width in enumerate((88, 88, 92, 76, 48, 88)):  # Code, Name, Sex, Status, Obs, Edit
            self.table.setColumnWidth(column, width)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_select)
        self.table.cellDoubleClicked.connect(self._on_row_double_clicked)  # double-click also edits
        splitter.addWidget(self.table)

        detail = QWidget()
        detail_layout = QVBoxLayout(detail)
        detail_layout.setContentsMargins(6, 0, 0, 0)

        self.individual_header = QLabel()
        self.individual_header.setStyleSheet("font-size: 15px; font-weight: 700;")
        detail_layout.addWidget(self.individual_header)

        self.viewer = ImageViewer()
        detail_layout.addWidget(self.viewer, 3)

        # Arrows step through every observation (capture) of the selected individual.
        nav_row = QHBoxLayout()
        self.prev_button = QPushButton("◀")
        self.prev_button.setToolTip("Previous observation of this individual")
        self.prev_button.setFixedWidth(40)
        self.prev_button.clicked.connect(lambda: self._step_observation(-1))
        self.next_button = QPushButton("▶")
        self.next_button.setToolTip("Next observation of this individual")
        self.next_button.setFixedWidth(40)
        self.next_button.clicked.connect(lambda: self._step_observation(1))
        self.obs_position_label = QLabel()
        self.obs_position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav_row.addWidget(self.prev_button)
        nav_row.addWidget(self.obs_position_label, 1)
        nav_row.addWidget(self.next_button)
        detail_layout.addLayout(nav_row)

        detail_layout.addWidget(QLabel("<b>Observation details</b>"))
        data_row = QHBoxLayout()
        self.info_table = InfoTable()
        data_row.addWidget(self.info_table, 1)
        roi_box = QVBoxLayout()
        roi_box.addWidget(QLabel("ROI"))
        self.roi_preview = RoiPreview()
        roi_box.addWidget(self.roi_preview)  # the ROI crop beside the data for visual comparison
        roi_box.addStretch(1)
        data_row.addLayout(roi_box)
        detail_layout.addLayout(data_row, 2)
        splitter.addWidget(detail)

        splitter.setStretchFactor(0, 0)  # table hugs its content
        splitter.setStretchFactor(1, 1)  # detail panel gets the space
        splitter.setSizes([520, 700])
        layout.addWidget(splitter)

        state.project_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        catalog = self._state.catalog
        self.viewer.clear()
        self.info_table.clear_rows()
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
            cells = [
                individual.code,
                individual.name,
                str(individual.sex),
                str(individual.status),
                str(count),
            ]
            for column, text in enumerate(cells):
                self.table.setItem(row, column, QTableWidgetItem(text))
            edit_button = QPushButton("Edit")
            edit_button.setStyleSheet("padding: 3px 12px;")  # override the heavy global button padding
            edit_button.clicked.connect(lambda _=False, ind=individual: self._edit_individual(ind))
            holder = QWidget()  # centre the button so it is never clipped by the cell
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(6, 2, 6, 2)
            holder_layout.addStretch(1)
            holder_layout.addWidget(edit_button)
            holder_layout.addStretch(1)
            self.table.setCellWidget(row, len(_COLUMNS) - 1, holder)
        if self._individuals:
            self.table.selectRow(0)

    def _on_row_double_clicked(self, row: int, _column: int) -> None:
        if 0 <= row < len(self._individuals):
            self._edit_individual(self._individuals[row])

    def _representative_observation(self, individual: Individual) -> Observation | None:
        catalog = self._state.catalog
        if catalog is None or individual.id is None:
            return None
        observations = catalog.observations_for_individual(individual.id)
        return observations[0] if observations else None

    def _on_select(self) -> None:
        catalog = self._state.catalog
        row = self.table.currentRow()
        self._individual_observations = []
        self._obs_index = 0
        if catalog is None or not 0 <= row < len(self._individuals):
            self.individual_header.setText("")
            self._render_observation()
            return
        individual = self._individuals[row]
        if individual.id is None:
            return
        self._individual_observations = catalog.observations_for_individual(individual.id)

        count = len(self._individual_observations)
        parts = [individual.code]
        if individual.name:
            parts.append(individual.name)
        parts.extend(
            (str(individual.sex), str(individual.status), f"{count} observation{'' if count == 1 else 's'}")
        )
        self.individual_header.setText("  ·  ".join(parts))
        self._render_observation()

    def _step_observation(self, delta: int) -> None:
        target = self._obs_index + delta
        if 0 <= target < len(self._individual_observations):
            self._obs_index = target
            self._render_observation()

    def _update_nav_buttons(self) -> None:
        count = len(self._individual_observations)
        self.prev_button.setEnabled(self._obs_index > 0)
        self.next_button.setEnabled(self._obs_index < count - 1)

    def _render_observation(self) -> None:
        """Show the current observation of the selected individual: image, ROI, date and details."""
        self.viewer.clear()
        self.info_table.clear_rows()
        self.roi_preview.clear_preview()
        self._update_nav_buttons()
        project = self._state.project
        catalog = self._state.catalog
        count = len(self._individual_observations)
        if count == 0 or project is None or catalog is None:
            self.obs_position_label.setText("")
            return
        self._obs_index = max(0, min(self._obs_index, count - 1))
        observation = self._individual_observations[self._obs_index]
        date = format_date(observation.observed_at) or "no date"
        self.obs_position_label.setText(f"Observation {self._obs_index + 1} of {count}  ·  {date}")

        image = None
        roi = None
        if observation.id is not None:
            images = catalog.images_for(observation.id)
            if images:
                try:
                    image = project.image_store.load(images[0].rel_path)
                    self.viewer.set_image(image)
                except (OSError, ValueError):
                    image = None
                if images[0].id is not None:
                    roi = catalog.get_image_roi(images[0].id)
        fields = species_field_definitions(self._state, observation.species_id)
        self.info_table.show_rows(observation_info_rows(observation, fields))
        self.roi_preview.show_roi(image, roi)

    def _edit_individual(self, individual: Individual) -> None:
        catalog = self._state.catalog
        if catalog is None or individual.id is None:
            return
        fields = species_field_definitions(self._state, individual.species_id)
        representative = self._representative_observation(individual)
        measurements = dict(representative.measurements) if representative is not None else {}
        dialog = IndividualEditDialog(individual, fields, measurements, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        catalog.update_individual(dialog.updated_individual())
        new_measurements = dialog.measurement_values()
        if representative is not None and new_measurements != representative.measurements:
            representative.measurements = new_measurements
            catalog.update_observation(representative)
        self._state.project_changed.emit()
