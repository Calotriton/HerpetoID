"""Observation editor: browse observations, mark the ventral ROI, and enter measurements.

Left: the observation table. Right: the image with an ROI drawing tool, plus a form (universal fields
+ the species' auto-generated measurement fields) and a Save button.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from herpetoid.api import FieldDefinition
from herpetoid.domain import Image, Location, Observation
from herpetoid.gui.state import AppState
from herpetoid.gui.widgets.dynamic_form import DynamicForm
from herpetoid.gui.widgets.roi_image_viewer import RoiImageViewer

_COLUMNS = ["ID", "Species", "Observer", "Individual"]


def _parse_float(text: str) -> float | None:
    text = text.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class ObservationsScreen(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._observations: list[Observation] = []
        self._species_names: dict[int | None, str] = {}
        self._current: Observation | None = None
        self._current_image: Image | None = None
        self._form: DynamicForm | None = None

        layout = QHBoxLayout(self)
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
        splitter.addWidget(self.table)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(6, 0, 0, 0)

        self.viewer = RoiImageViewer()
        right_layout.addWidget(self.viewer, 3)

        roi_row = QHBoxLayout()
        self.draw_button = QPushButton("Draw ventral ROI")
        self.draw_button.setCheckable(True)
        self.draw_button.toggled.connect(self.viewer.set_draw_mode)
        clear_roi_button = QPushButton("Clear ROI")
        clear_roi_button.clicked.connect(self.viewer.clear_roi)
        roi_row.addWidget(self.draw_button)
        roi_row.addWidget(clear_roi_button)
        roi_row.addStretch(1)
        right_layout.addLayout(roi_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_host = QWidget()
        self._form_layout = QVBoxLayout(form_host)

        universal = QWidget()
        universal_form = QFormLayout(universal)
        self.observer_edit = QLineEdit()
        universal_form.addRow("Observer", self.observer_edit)
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(QDate.currentDate())
        universal_form.addRow("Date", self.date_edit)
        self.notes_edit = QLineEdit()
        universal_form.addRow("Notes", self.notes_edit)
        self.lat_edit = QLineEdit()
        self.lat_edit.setPlaceholderText("e.g. 42.5")
        universal_form.addRow("Latitude", self.lat_edit)
        self.lon_edit = QLineEdit()
        self.lon_edit.setPlaceholderText("e.g. 1.0")
        universal_form.addRow("Longitude", self.lon_edit)
        self.location_edit = QLineEdit()
        universal_form.addRow("Location", self.location_edit)
        self._form_layout.addWidget(universal)

        self._form_layout.addWidget(QLabel("<b>Measurements</b>"))
        self._form_container = QWidget()
        self._form_container_layout = QVBoxLayout(self._form_container)
        self._form_container_layout.setContentsMargins(0, 0, 0, 0)
        self._form_layout.addWidget(self._form_container)
        self._form_layout.addStretch(1)
        scroll.setWidget(form_host)
        right_layout.addWidget(scroll, 4)

        bottom = QHBoxLayout()
        self.status_label = QLabel()
        bottom.addWidget(self.status_label)
        bottom.addStretch(1)
        self.save_button = QPushButton("Save observation")
        self.save_button.clicked.connect(self.save)
        bottom.addWidget(self.save_button)
        right_layout.addLayout(bottom)

        splitter.addWidget(right)
        splitter.setSizes([380, 720])
        layout.addWidget(splitter)

        self._set_editing_enabled(False)
        state.project_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        catalog = self._state.catalog
        selected_id = self._current.id if self._current is not None else None
        if catalog is None:
            self._observations = []
            self.table.setRowCount(0)
            self._clear_editor()
            return

        self._species_names = {s.id: s.scientific_name for s in catalog.list_species()}
        individuals = {i.id: i.code for i in catalog.list_individuals()}
        self._observations = catalog.list_observations()

        self.table.blockSignals(True)
        self.table.setRowCount(len(self._observations))
        for row, obs in enumerate(self._observations):
            code = individuals.get(obs.individual_id, "") if obs.individual_id else ""
            cells = [str(obs.id), self._species_names.get(obs.species_id, ""), obs.observer, code]
            for column, text in enumerate(cells):
                self.table.setItem(row, column, QTableWidgetItem(text))
        self.table.blockSignals(False)

        if not self._observations:
            self._clear_editor()
            return
        target = 0
        if selected_id is not None:
            for row, obs in enumerate(self._observations):
                if obs.id == selected_id:
                    target = row
                    break
        self.table.selectRow(target)

    def _on_select(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._observations):
            self._load_observation(self._observations[row])

    def _load_observation(self, observation: Observation) -> None:
        self._current = observation
        self._set_editing_enabled(True)
        self.observer_edit.setText(observation.observer)
        moment = observation.observed_at
        if moment is not None:
            self.date_edit.setDate(QDate(moment.year, moment.month, moment.day))
        else:
            self.date_edit.setDate(QDate.currentDate())
        self.notes_edit.setText(observation.notes)
        location = observation.location
        self.lat_edit.setText("" if location.latitude is None else str(location.latitude))
        self.lon_edit.setText("" if location.longitude is None else str(location.longitude))
        self.location_edit.setText(location.name or "")
        self._build_form(observation.species_id, observation.measurements)
        self._load_image(observation)

    def _build_form(self, species_id: int, values: dict[str, Any]) -> None:
        if self._form is not None:
            self._form.setParent(None)
            self._form = None
        self._form = DynamicForm(self._species_fields(species_id))
        self._form.set_values(values)
        self._form_container_layout.addWidget(self._form)

    def _species_fields(self, species_id: int) -> list[FieldDefinition]:
        catalog = self._state.catalog
        if catalog is None:
            return []
        species = catalog.get_species(species_id)
        if species is None or species.module is None:
            return []
        if self._state.registry.module(species.module.plugin_id) is None:
            return []
        try:
            module = self._state.registry.create_module(species.module.plugin_id)
            return list(module.define_observation_fields())
        except Exception:  # a broken module must not break the editor
            return []

    def _load_image(self, observation: Observation) -> None:
        self.draw_button.setChecked(False)
        self.viewer.clear()
        self.viewer.clear_roi()
        self._current_image = None
        catalog = self._state.catalog
        project = self._state.project
        if catalog is None or project is None or observation.id is None:
            return
        images = catalog.images_for(observation.id)
        if not images:
            return
        self._current_image = images[0]
        try:
            self.viewer.set_image(project.image_store.load(self._current_image.rel_path))
        except (OSError, ValueError):
            self.viewer.clear()
            return
        if self._current_image.id is not None:
            self.viewer.set_roi(catalog.get_image_roi(self._current_image.id))

    def save(self) -> None:
        observation = self._current
        catalog = self._state.catalog
        if observation is None or catalog is None:
            return
        observation.observer = self.observer_edit.text().strip()
        qdate = self.date_edit.date()
        observation.observed_at = date(qdate.year(), qdate.month(), qdate.day())
        observation.notes = self.notes_edit.text().strip()
        try:
            observation.location = Location(
                latitude=_parse_float(self.lat_edit.text()),
                longitude=_parse_float(self.lon_edit.text()),
                name=self.location_edit.text().strip() or None,
            )
        except ValueError as exc:
            self.status_label.setText(f"Invalid location: {exc}")
            return
        if self._form is not None:
            observation.measurements = {
                key: value for key, value in self._form.values().items() if value is not None
            }
        catalog.update_observation(observation)
        if self._current_image is not None and self._current_image.id is not None:
            roi = self.viewer.roi()
            if roi is not None:
                catalog.set_image_roi(self._current_image.id, roi)
        self.status_label.setText("Saved.")
        self._state.project_changed.emit()

    def _set_editing_enabled(self, enabled: bool) -> None:
        for widget in (
            self.observer_edit,
            self.date_edit,
            self.notes_edit,
            self.lat_edit,
            self.lon_edit,
            self.location_edit,
            self.save_button,
            self.draw_button,
        ):
            widget.setEnabled(enabled)

    def _clear_editor(self) -> None:
        self._current = None
        self._current_image = None
        self.viewer.clear()
        self.viewer.clear_roi()
        for edit in (
            self.observer_edit,
            self.notes_edit,
            self.lat_edit,
            self.lon_edit,
            self.location_edit,
        ):
            edit.clear()
        if self._form is not None:
            self._form.setParent(None)
            self._form = None
        self._set_editing_enabled(False)
