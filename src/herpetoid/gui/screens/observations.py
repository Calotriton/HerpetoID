"""Observation editor: browse observations, mark the ventral ROI, and enter measurements.

Left: the observation table. Right: the image with an ROI drawing tool, plus a form (universal fields
+ the species' auto-generated measurement fields) and a Save button.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QColor, QPixmap
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
from herpetoid.application.catalog_service import (
    PENDING_CODE_KEY,
    SAVED_KEY,
    is_saved,
    pending_code,
)
from herpetoid.domain import Image, Location, Observation
from herpetoid.gui.state import AppState
from herpetoid.gui.theme import section_label
from herpetoid.gui.widgets.dynamic_form import DynamicForm
from herpetoid.gui.widgets.image_viewer import ndarray_to_qimage
from herpetoid.gui.widgets.roi_image_viewer import RoiImageViewer
from herpetoid.gui.widgets.toast import Toast

# Species is intentionally omitted from this list (it's redundant per-row and shown in the editor).
# "Saved" = has a saved ROI; "Ident." = assigned to an individual (queried & identified);
# "Type" = New individual vs Recapture.
_COLUMNS = ["ID", "Observer", "Indiv.", "Saved", "Ident.", "Type"]


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
        self._current: Observation | None = None
        self._current_image: Image | None = None
        self._form: DynamicForm | None = None
        self._locked = False  # saved observations open read-only behind the "Edit" button

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # --- Left: a narrow list of observations ---------------------------------------------
        table_panel = QWidget()
        table_layout = QVBoxLayout(table_panel)
        table_layout.setContentsMargins(0, 0, 0, 0)
        table_layout.addWidget(section_label("Observations"))
        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.setAlternatingRowColors(True)
        table_header = self.table.horizontalHeader()
        # Every column is user-resizable (drag the header edges); text elides to whatever width you set.
        for column in range(len(_COLUMNS)):
            table_header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
        for column, width in enumerate((30, 78, 66, 46, 56, 74)):
            self.table.setColumnWidth(column, width)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        for index, tip in (
            (3, "A tick means the observation has a saved ROI — ready to identify."),
            (4, "A tick means it has been assigned to an individual (queried & identified)."),
            (5, "Whether this capture established a New individual or is a Recapture of a known one."),
        ):
            header_item = self.table.horizontalHeaderItem(index)
            if header_item is not None:
                header_item.setToolTip(tip)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_select)
        table_layout.addWidget(self.table, 1)
        table_panel.setMinimumWidth(300)
        table_panel.setMaximumWidth(540)
        splitter.addWidget(table_panel)

        # --- Centre: the image + ROI tools (this pane gets the space) ------------------------
        image_area = QWidget()
        image_layout = QVBoxLayout(image_area)
        image_layout.setContentsMargins(6, 0, 6, 0)

        self.viewer = RoiImageViewer()
        self.viewer.roi_changed.connect(self._update_preview)
        image_layout.addWidget(self.viewer, 1)

        self.guidance_label = QLabel()
        self.guidance_label.setWordWrap(True)
        self.guidance_label.setStyleSheet("color: palette(mid);")
        image_layout.addWidget(self.guidance_label)

        controls_and_preview = QHBoxLayout()
        controls = QVBoxLayout()

        roi_group = QGroupBox("Region of interest")
        roi_row = QHBoxLayout(roi_group)
        self.draw_button = QPushButton("Draw ROI")
        self.draw_button.setCheckable(True)
        self.draw_button.toggled.connect(self.viewer.set_draw_mode)
        self.draw_button.toggled.connect(self._on_draw_toggled)
        clear_roi_button = QPushButton("Clear ROI")
        clear_roi_button.clicked.connect(self.viewer.clear_roi)
        # Polygon is placed by clicking points; right-click removes the last point, double-click closes
        # it — so no separate Finish/Undo buttons are needed.
        for widget in (self.draw_button, clear_roi_button):
            roi_row.addWidget(widget)
        roi_row.addStretch(1)
        # Rotate / reset live as a small floating toolbar in the image's corner (see RoiImageViewer),
        # so the ROI tools get the full width here.
        controls.addWidget(roi_group)
        controls.addStretch(1)
        controls_and_preview.addLayout(controls, 1)

        preview_group = QGroupBox("Selected area")
        preview_layout = QVBoxLayout(preview_group)
        preview_layout.setContentsMargins(6, 6, 6, 6)
        self.preview_label = QLabel("No ROI")
        self.preview_label.setFixedSize(200, 150)
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_label.setFrameShape(QFrame.Shape.StyledPanel)
        preview_layout.addWidget(self.preview_label)
        controls_and_preview.addWidget(preview_group)
        image_layout.addLayout(controls_and_preview)
        splitter.addWidget(image_area)

        # --- Right: a compact data-entry column ----------------------------------------------
        form_panel = QWidget()
        form_panel_layout = QVBoxLayout(form_panel)
        form_panel_layout.setContentsMargins(0, 0, 0, 0)
        form_panel_layout.addWidget(section_label("Observation details"))

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_host = QWidget()
        self._form_layout = QVBoxLayout(form_host)
        self._form_layout.setContentsMargins(0, 0, 0, 0)

        universal = QWidget()
        universal_form = QFormLayout(universal)
        universal_form.setContentsMargins(0, 0, 0, 0)
        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText("e.g. CA-001 — links a known individual")
        self.code_edit.setToolTip(
            "A code matching a cataloged individual links this observation to it.\n"
            "A new code stays pending until you confirm it on the Identification tab."
        )
        universal_form.addRow("Individual code", self.code_edit)
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

        self._form_layout.addWidget(section_label("Measurements"))
        self._form_container = QWidget()
        self._form_container_layout = QVBoxLayout(self._form_container)
        self._form_container_layout.setContentsMargins(0, 0, 0, 0)
        self._form_layout.addWidget(self._form_container)
        self._form_layout.addStretch(1)
        scroll.setWidget(form_host)
        form_panel_layout.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        bottom.addWidget(self.status_label, 1)
        self.save_button = QPushButton("Save observation")
        self.save_button.setObjectName("primary")
        self.save_button.clicked.connect(self._on_save_clicked)
        bottom.addWidget(self.save_button)
        form_panel_layout.addLayout(bottom)
        form_panel.setMinimumWidth(260)
        form_panel.setMaximumWidth(380)
        splitter.addWidget(form_panel)

        splitter.setStretchFactor(0, 0)  # table: fixed-ish
        splitter.setStretchFactor(1, 1)  # image: takes all extra space
        splitter.setStretchFactor(2, 0)  # form: fixed-ish
        splitter.setSizes([430, 590, 320])
        layout.addWidget(splitter)

        self.toast = Toast(self)
        self._set_editing_enabled(False)
        state.project_changed.connect(self._refresh)
        self._refresh()

    @staticmethod
    def _tick_item(on: bool, tooltip: str) -> QTableWidgetItem:
        item = QTableWidgetItem("✓" if on else "")
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if on:
            item.setForeground(QColor(64, 200, 64))
            item.setToolTip(tooltip)
        return item

    def _refresh(self) -> None:
        catalog = self._state.catalog
        selected_id = self._current.id if self._current is not None else None
        if catalog is None:
            self._observations = []
            self.table.setRowCount(0)
            self._clear_editor()
            return

        individuals = {i.id: i.code for i in catalog.list_individuals()}
        self._observations = catalog.list_observations()
        # "Identified" reflects an actual identification run in Candidates — not merely having an
        # individual code assigned in this editor.
        identified_ids = catalog.identified_observation_ids()
        # The earliest-created observation of each individual is the "New" record; the rest are
        # recaptures (this is what confirming a match in Candidates produces).
        first_for_individual: dict[int, int | None] = {}
        for obs in sorted(self._observations, key=lambda o: (o.id or 0)):
            if obs.individual_id is not None:
                first_for_individual.setdefault(obs.individual_id, obs.id)

        self.table.blockSignals(True)
        self.table.setRowCount(len(self._observations))
        for row, obs in enumerate(self._observations):
            code = individuals.get(obs.individual_id, "") if obs.individual_id else ""
            if not code and (pending := pending_code(obs)):
                code = f"{pending} ?"  # typed but unconfirmed — confirm on the Identification tab
            for column, text in enumerate((str(obs.id), obs.observer, code)):
                self.table.setItem(row, column, QTableWidgetItem(text))
            if code.endswith(" ?") and (item := self.table.item(row, 2)) is not None:
                item.setToolTip("Pending code — confirm it on the Identification tab.")

            has_roi = obs.id is not None and catalog.has_roi(obs.id)
            self.table.setItem(row, 3, self._tick_item(has_roi, "Saved with a ROI"))

            individual_id = obs.individual_id
            self.table.setItem(
                row, 4, self._tick_item(obs.id in identified_ids, "Run through identification")
            )

            if individual_id is None:
                type_text = ""
            elif obs.id == first_for_individual.get(individual_id):
                type_text = "New"
            else:
                type_text = "Recapture"
            self.table.setItem(row, 5, QTableWidgetItem(type_text))
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
        if self._current is not self._observations[target]:
            # selectRow fires no selection signal when the row index is unchanged, which would leave
            # the editor holding a stale copy (e.g. its individual_id from before a confirm on the
            # Identification tab) — saving that copy would silently drop the assignment.
            self._load_observation(self._observations[target])

    def _on_select(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self._observations):
            self._load_observation(self._observations[row])

    def select_observation(self, observation_id: int) -> None:
        """Select (and load) the observation with the given id, if present."""
        for row, obs in enumerate(self._observations):
            if obs.id == observation_id:
                self.table.selectRow(row)
                return

    def _load_observation(self, observation: Observation) -> None:
        self._current = observation
        self._set_editing_enabled(True)
        self.code_edit.setText(self._individual_code(observation))
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
        # Already-saved observations open locked behind "Edit"; fresh ones are directly editable.
        self._apply_locked(is_saved(observation))

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
        if is_polygon:
            self.guidance_label.setText(
                "Click to place points around the region · right-click removes the last point · "
                "double-click to close."
            )
            if spec is not None and spec.guidance:
                self.guidance_label.setText(
                    f"{spec.guidance}  (Right-click undoes the last point; double-click closes.)"
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

    def _on_save_clicked(self) -> None:
        """The one bottom button: saves when editable, unlocks for editing when locked."""
        if self._locked:
            self._apply_locked(False)
            self.status_label.setText("Editing — make your changes and press “Save changes”.")
            return
        self.save()

    def save(self) -> None:
        observation = self._current
        catalog = self._state.catalog
        if observation is None or catalog is None:
            return
        was_saved = is_saved(observation)
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
        observation.measurements[SAVED_KEY] = True
        # A code matching a cataloged individual links the observation to it. A *new* code does NOT
        # create the individual here — it is kept pending until the user confirms it on the
        # Identification tab ("Mark query as new individual") — UNLESS the observation is already
        # confirmed to an individual: then the new code simply renames that individual (the
        # confirmed identity is kept; no re-identification needed). Clearing the code unassigns.
        status = "Edits saved successfully." if was_saved else "Observation saved successfully."
        headline = status
        code = self.code_edit.text().strip()
        assigned = (
            catalog.get_individual(observation.individual_id)
            if observation.individual_id is not None
            else None
        )
        if code:
            individual = catalog.find_individual_by_code(observation.species_id, code)
            if individual is not None:
                observation.individual_id = individual.id
                observation.measurements.pop(PENDING_CODE_KEY, None)
            elif assigned is not None:
                old_code = assigned.code
                assigned.code = code
                catalog.update_individual(assigned)
                observation.measurements.pop(PENDING_CODE_KEY, None)
                status = f"{headline} Individual “{old_code}” renamed to “{code}”."
            else:
                observation.individual_id = None
                observation.measurements[PENDING_CODE_KEY] = code
                status = (
                    f"{headline} Code “{code}” is pending — confirm it as a new individual on the "
                    "Identification tab."
                )
        else:
            observation.individual_id = None
        catalog.update_observation(observation)
        if self._current_image is not None and self._current_image.id is not None:
            roi = self.viewer.roi()
            if roi is not None:
                catalog.set_image_roi(self._current_image.id, roi)
        missing = self._missing_details()
        if missing:
            missing_note = f"Missing information: {', '.join(missing)}."
            self.toast.show_message(f"{headline}\n{missing_note}")
            self.status_label.setText(f"{status} {missing_note}")
        else:
            self.toast.show_message(f"{headline}\nAll details are complete.")
            self.status_label.setText(status)
        self._state.project_changed.emit()

    def _missing_details(self) -> list[str]:
        """Human-readable names of the details the user has not filled in yet."""
        missing: list[str] = []
        if not self.code_edit.text().strip():
            missing.append("Individual code")
        if not self.observer_edit.text().strip():
            missing.append("Observer")
        if not self.notes_edit.text().strip():
            missing.append("Notes")
        if _parse_float(self.lat_edit.text()) is None:
            missing.append("Latitude")
        if _parse_float(self.lon_edit.text()) is None:
            missing.append("Longitude")
        if not self.location_edit.text().strip():
            missing.append("Location")
        if self._form is not None:
            missing.extend(self._form.missing_labels())
        if self.viewer.roi() is None:
            missing.append("ROI")
        return missing

    def _individual_code(self, observation: Observation) -> str:
        catalog = self._state.catalog
        if catalog is None or observation.individual_id is None:
            return pending_code(observation) or ""
        individual = catalog.get_individual(observation.individual_id)
        return individual.code if individual is not None else ""

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
            self.code_edit,
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

    def _apply_locked(self, locked: bool) -> None:
        """Lock (read-only behind "Edit") or unlock the editor for the current observation."""
        self._locked = locked
        if locked:
            self.draw_button.setChecked(False)
        for widget in (
            self.code_edit,
            self.observer_edit,
            self.date_edit,
            self.notes_edit,
            self.lat_edit,
            self.lon_edit,
            self.location_edit,
            self.draw_button,
        ):
            widget.setEnabled(not locked)
        if self._form is not None:
            self._form.setEnabled(not locked)
        if locked:
            self.save_button.setText("Edit")
        else:
            already_saved = self._current is not None and is_saved(self._current)
            self.save_button.setText("Save changes" if already_saved else "Save observation")

    def _clear_editor(self) -> None:
        self._current = None
        self._current_image = None
        self.viewer.clear()
        self.viewer.clear_roi()
        for edit in (
            self.code_edit,
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
        self._locked = False
        self.save_button.setText("Save observation")
        self._set_editing_enabled(False)
