"""Candidate Ranking + Comparison: run identification, review ranked candidates side-by-side, confirm.

The software proposes ranked candidates; the scientist makes the final call (confirm a match, or mark
the query as a new individual).
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from herpetoid.api import ROI
from herpetoid.application.identification_runner import Candidate, IdentificationRunner
from herpetoid.gui.state import AppState
from herpetoid.gui.widgets.image_viewer import ImageViewer
from herpetoid.gui.widgets.info_table import (
    InfoTable,
    observation_info_rows,
    species_field_definitions,
)
from herpetoid.gui.widgets.roi_preview import RoiPreview


def _viewer_panel(title: str) -> tuple[QWidget, ImageViewer, InfoTable, RoiPreview]:
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(QLabel(f"<b>{title}</b>"))
    viewer = ImageViewer()
    layout.addWidget(viewer, 3)
    data_row = QHBoxLayout()
    info = InfoTable()
    data_row.addWidget(info, 1)
    roi_box = QVBoxLayout()
    roi_box.addWidget(QLabel("ROI"))
    roi_preview = RoiPreview()
    roi_box.addWidget(roi_preview)
    roi_box.addStretch(1)
    data_row.addLayout(roi_box)  # the ROI crop sits beside the data box for visual comparison
    layout.addLayout(data_row, 2)
    return panel, viewer, info, roi_preview


class CandidateRankingScreen(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._candidates: list[Candidate] = []
        self._query_observation_id: int | None = None
        self._species_names: dict[int | None, str] = {}
        self._species_by_obs: dict[int | None, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Query:"))
        self.query_combo = QComboBox()
        self.query_combo.setMinimumWidth(150)
        self.query_combo.currentIndexChanged.connect(self._update_query_species)
        controls.addWidget(self.query_combo)
        self.query_species_label = QLabel()
        self.query_species_label.setStyleSheet("color: palette(mid);")
        controls.addWidget(self.query_species_label)
        controls.addStretch(1)
        controls.addWidget(QLabel("Algorithm:"))
        self.algorithm_combo = QComboBox()
        controls.addWidget(self.algorithm_combo)
        self.identify_button = QPushButton("Identify")
        self.identify_button.setObjectName("primary")
        self.identify_button.clicked.connect(self.identify)
        controls.addWidget(self.identify_button)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)

        rank_panel = QWidget()
        rank_layout = QVBoxLayout(rank_panel)
        rank_layout.setContentsMargins(0, 0, 0, 0)
        rank_layout.addWidget(QLabel("<b>Ranked candidates</b>"))
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "Observation", "Individual", "Score"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # #
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # Observation
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)  # Individual
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Score
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.itemSelectionChanged.connect(self._on_candidate_select)
        rank_layout.addWidget(self.table, 1)
        rank_panel.setMinimumWidth(240)
        rank_panel.setMaximumWidth(360)
        splitter.addWidget(rank_panel)

        comparison = QWidget()
        comparison_layout = QHBoxLayout(comparison)
        comparison_layout.setContentsMargins(0, 0, 0, 0)
        query_panel, self.query_viewer, self.query_info, self.query_roi = _viewer_panel("Query")
        (
            candidate_panel,
            self.candidate_viewer,
            self.candidate_info,
            self.candidate_roi,
        ) = _viewer_panel("Candidate")
        comparison_layout.addWidget(query_panel)
        comparison_layout.addWidget(candidate_panel)
        splitter.addWidget(comparison)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([300, 900])
        layout.addWidget(splitter, 1)

        actions = QHBoxLayout()
        self.status_label = QLabel()
        actions.addWidget(self.status_label)
        actions.addStretch(1)
        self.new_button = QPushButton("Mark query as new individual")
        self.new_button.clicked.connect(self.mark_new)
        self.confirm_button = QPushButton("Confirm same individual")
        self.confirm_button.setObjectName("primary")
        self.confirm_button.clicked.connect(self.confirm_same)
        actions.addWidget(self.new_button)
        actions.addWidget(self.confirm_button)
        layout.addLayout(actions)

        state.project_changed.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        self._candidates = []
        self._query_observation_id = None
        self.table.setRowCount(0)
        self.query_viewer.clear()
        self.candidate_viewer.clear()
        self.query_info.clear_rows()
        self.candidate_info.clear_rows()
        self.query_roi.clear_preview()
        self.candidate_roi.clear_preview()
        self._populate_queries()
        self._populate_algorithms()
        has_project = self._state.project is not None
        has_queries = self.query_combo.count() > 0
        for widget in (self.query_combo, self.algorithm_combo, self.identify_button):
            widget.setEnabled(has_project and has_queries)
        if not has_project:
            self.status_label.setText("Open a project first.")
        elif not has_queries:
            self.status_label.setText(
                "Nothing to identify yet — mark a ROI on an observation (Observations tab) first."
            )
        else:
            self.status_label.setText("")
        self._update_action_buttons()

    def _populate_queries(self) -> None:
        self.query_combo.clear()
        catalog = self._state.catalog
        if catalog is None:
            return
        self._species_names = {s.id: s.scientific_name for s in catalog.list_species()}
        self._species_by_obs = {}
        codes = {i.id: i.code for i in catalog.list_individuals()}
        # Any observation with a marked ROI can be identified (assigned or not). The dropdown shows
        # just the code (the species is shown once, next to it, to avoid repeating it on every row).
        for obs in catalog.comparable_observations():
            code = codes.get(obs.individual_id) if obs.individual_id else None
            label = code if code else f"Obs {obs.id} (unassigned)"
            self.query_combo.addItem(label, obs.id)
            self._species_by_obs[obs.id] = self._species_names.get(obs.species_id, "")
        self._update_query_species()

    def _update_query_species(self) -> None:
        obs_id = self.query_combo.currentData()
        species = self._species_by_obs.get(obs_id, "") if obs_id is not None else ""
        self.query_species_label.setText(f"Species: {species}" if species else "")

    def _populate_algorithms(self) -> None:
        self.algorithm_combo.clear()
        for record in self._state.registry.algorithms(enabled_only=True):
            self.algorithm_combo.addItem(record.descriptor.name, record.descriptor.algorithm_id)

    def identify(self) -> None:
        project = self._state.project
        query_id = self.query_combo.currentData()
        algorithm_id = self.algorithm_combo.currentData()
        if project is None or query_id is None or algorithm_id is None:
            return
        self._query_observation_id = int(query_id)
        runner = IdentificationRunner(project, self._state.registry, self._state.identification)
        top_k = self._state.settings.settings.default_top_k
        try:
            self._candidates = runner.identify(int(query_id), str(algorithm_id), top_k=top_k)
        except Exception as exc:  # surface any plugin failure without crashing
            self.status_label.setText(f"Identification failed: {exc}")
            return

        # Record that this observation was actually run through identification (drives the
        # Observations "Ident." column) — distinct from merely having an individual code assigned.
        catalog = self._state.catalog
        if catalog is not None:
            catalog.record_identification(self._query_observation_id, str(algorithm_id))

        self._show_image(self.query_viewer, self._query_observation_id)
        self._show_observation_info(self.query_info, self.query_roi, self._query_observation_id)
        self.candidate_info.clear_rows()
        self.candidate_roi.clear_preview()
        self.table.setRowCount(len(self._candidates))
        for row, candidate in enumerate(self._candidates):
            individual = candidate.individual.code if candidate.individual else "-"
            cells = [
                str(candidate.rank),
                f"Obs {candidate.observation.id}",
                individual,
                f"{candidate.normalized_score:.3f}",
            ]
            for column, text in enumerate(cells):
                self.table.setItem(row, column, QTableWidgetItem(text))
        if self._candidates:
            self.table.selectRow(0)
        self.status_label.setText(
            f"{len(self._candidates)} candidate(s) — the final decision is yours."
            if self._candidates
            else "No other observations to compare against yet."
        )
        self._update_action_buttons()

    def _on_candidate_select(self) -> None:
        candidate = self._selected_candidate()
        if candidate is not None:
            self._show_rel_path(self.candidate_viewer, candidate.image.rel_path)
            code = candidate.individual.code if candidate.individual is not None else None
            self._show_observation_info(
                self.candidate_info,
                self.candidate_roi,
                candidate.observation.id,
                individual_code=code,
            )
        self._update_action_buttons()

    def _show_observation_info(
        self,
        info_table: InfoTable,
        roi_preview: RoiPreview,
        observation_id: int | None,
        *,
        individual_code: str | None = None,
    ) -> None:
        info_table.clear_rows()
        roi_preview.clear_preview()
        catalog = self._state.catalog
        if catalog is None or observation_id is None:
            return
        observation = catalog.get_observation(observation_id)
        if observation is None:
            return
        code = individual_code
        if code is None and observation.individual_id is not None:
            individual = catalog.get_individual(observation.individual_id)
            code = individual.code if individual is not None else None
        fields = species_field_definitions(self._state, observation.species_id)
        info_table.show_rows(observation_info_rows(observation, fields, individual_code=code))
        image, roi = self._image_and_roi(observation_id)
        roi_preview.show_roi(image, roi)

    def _image_and_roi(self, observation_id: int) -> tuple[np.ndarray | None, ROI | None]:
        catalog = self._state.catalog
        project = self._state.project
        if catalog is None or project is None:
            return None, None
        images = catalog.images_for(observation_id)
        if not images or images[0].id is None:
            return None, None
        try:
            image = project.image_store.load(images[0].rel_path)
        except (OSError, ValueError):
            return None, None
        return image, catalog.get_image_roi(images[0].id)

    def _selected_candidate(self) -> Candidate | None:
        row = self.table.currentRow()
        return self._candidates[row] if 0 <= row < len(self._candidates) else None

    def _show_image(self, viewer: ImageViewer, observation_id: int) -> None:
        catalog = self._state.catalog
        if catalog is None:
            return
        images = catalog.images_for(observation_id)
        if images:
            self._show_rel_path(viewer, images[0].rel_path)

    def _show_rel_path(self, viewer: ImageViewer, rel_path: str) -> None:
        project = self._state.project
        if project is None:
            return
        try:
            viewer.set_image(project.image_store.load(rel_path))
        except (OSError, ValueError):
            viewer.clear()

    def _update_action_buttons(self) -> None:
        has_query = self._query_observation_id is not None
        self.confirm_button.setEnabled(has_query and self._selected_candidate() is not None)
        self.new_button.setEnabled(has_query)

    def confirm_same(self) -> None:
        candidate = self._selected_candidate()
        catalog = self._state.catalog
        if candidate is None or catalog is None or self._query_observation_id is None:
            return
        if candidate.individual is not None and candidate.individual.id is not None:
            catalog.link_observation(self._query_observation_id, candidate.individual.id)
            code = candidate.individual.code
        else:
            individual = catalog.create_individual(candidate.observation.species_id)
            if candidate.observation.id is not None:
                catalog.link_observation(candidate.observation.id, individual.id)
            catalog.link_observation(self._query_observation_id, individual.id)
            code = individual.code
        self.status_label.setText(f"Linked to individual {code}.")
        self._state.project_changed.emit()

    def mark_new(self) -> None:
        catalog = self._state.catalog
        if catalog is None or self._query_observation_id is None:
            return
        query = catalog.get_observation(self._query_observation_id)
        if query is None:
            return
        individual = catalog.create_individual(query.species_id)
        catalog.link_observation(self._query_observation_id, individual.id)
        self.status_label.setText(f"Created individual {individual.code}.")
        self._state.project_changed.emit()
