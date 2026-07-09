"""Observation editor: browse observations, mark the ventral ROI, and enter measurements.

Left: the observation table. Right: the image with an ROI drawing tool, plus a form (universal fields
+ the species' auto-generated measurement fields) and a Save button.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDateEdit,
    QFormLayout,
    QFrame,
    QGroupBox,
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

from herpetoid.api import FieldDefinition, ROIKind, ROISpec
from herpetoid.domain import Image, Location, Observation
from herpetoid.gui.state import AppState
from herpetoid.gui.widgets.dynamic_form import DynamicForm
from herpetoid.gui.widgets.image_viewer import ndarray_to_qimage
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
        self.viewer.roi_changed.connect(self._update_preview)
        right_layout.addWidget(self.viewer, 3)

        self.guidance_label = QLabel()
        self.guidance_label.setWordWrap(True)
        self.guidance_label.setStyleSheet("color: gray;")
        right_layout.addWidget(self.guidance_label)

        controls_and_preview = QHBoxLayout()
        controls = QVBoxLayout()

        roi_row = QHBoxLayout()
        self.draw_button = QPushButton("Draw ROI")
        self.draw_button.setCheckable(True)
        self.draw_button.toggled.connect(self.viewer.set_draw_mode)
        self.draw_button.toggled.connect(self._on_draw_toggled)
        self.finish_button = QPushButton("Finish polygon")
        self.finish_button.clicked.connect(self.viewer.finish_polygon)
        self.undo_button = QPushButton("Undo point")
        self.undo_button.clicked.connect(self.viewer.undo_point)
        clear_roi_button = QPushButton("Clear ROI")
        clear_roi_button.clicked.connect(self.viewer.clear_roi)
        for widget in (self.draw_button, self.finish_button, self.undo_button, clear_roi_button):
            roi_row.addWidget(widget)
        roi_row.addStretch(1)
        controls.addLayout(roi_row)

        view_row = QHBoxLayout()
        rotate_left = QPushButton("⟲ Rotate left")
        rotate_left.setToolTip("Turn the picture 90° counter-clockwise")
        rotate_left.clicked.connect(lambda: self.viewer.rotate_view(-90))
        rotate_right = QPushButton("Rotate right ⟳")
        rotate_right.setToolTip("Turn the picture 90° clockwise")
        rotate_right.clicked.connect(lambda: self.viewer.rotate_view(90))
        reset_view_button = QPushButton("Reset view")
        reset_view_button.setToolTip("Fit the whole picture and clear any rotation")
        reset_view_button.clicked.connect(self.viewer.reset_view)
        for widget in (rotate_left, rotate_right, reset_view_button):
            view_row.addWidget(widget)
        view_row.addStretch(1)
        controls.addLayout(view_row)
        controls.addStretch(1)
        self._view_buttons = (rotate_left, rotate_right, reset_view_button)
        controls_and_preview.addLayout(controls, 1)

        preview_group = QGroupBox("Selected area")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        self.preview_label = QLabel("No ROI")
        self.preview_label.setFixedSize(180, 140)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setFrameShape(QFrame.Shape.StyledPanel)
        preview_layout.addWidget(self.preview_label)
        controls_and_preview.addWidget(preview_group)
        right_layout.addLayout(controls_and_preview)

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
        self._configure_roi_tool(observation.species_id)
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

    def _species_roi_spec(self, species_id: int) -> ROISpec | None:
        catalog = self._state.catalog
        if catalog is None:
            return None
        species = catalog.get_species(species_id)
        if species is None or species.module is None:
            return None
        if self._state.registry.module(species.module.plugin_id) is None:
            return None
        try:
            module = self._state.registry.create_module(species.module.plugin_id)
            return module.define_species_profile().roi
        except Exception:  # a broken module must not break the editor
            return None

    def _configure_roi_tool(self, species_id: int) -> None:
        """Adapt the ROI tool to what the species declares (polygon vs rectangle + guidance)."""
        spec = self._species_roi_spec(species_id)
        kind = spec.kind if spec is not None else ROIKind.RECTANGLE
        self.viewer.set_roi_kind(kind)
        is_polygon = kind is ROIKind.POLYGON
        self.draw_button.setText("Draw polygon" if is_polygon else "Draw ROI")
        self.finish_button.setVisible(is_polygon)
        self.undo_button.setVisible(is_polygon)
        if spec is not None and spec.guidance:
            self.guidance_label.setText(spec.guidance)
        elif is_polygon:
            self.guidance_label.setText(
                "Click to place points around the region; double-click (or Finish) to close it."
            )
        else:
            self.guidance_label.setText("Drag a box around the pattern region.")

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

    def _on_draw_toggled(self, checked: bool) -> None:
        self.status_label.setText("Marking ROI — drawing enabled." if checked else "")

    def _update_preview(self) -> None:
        preview = self.viewer.roi_preview()
        if preview is None:
            self.preview_label.setPixmap(QPixmap())
            self.preview_label.setText("No ROI")
            return
        pixmap = QPixmap.fromImage(ndarray_to_qimage(preview)).scaled(
            self.preview_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_label.setPixmap(pixmap)

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
            self.finish_button,
            self.undo_button,
            *self._view_buttons,
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
