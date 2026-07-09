"""Candidate Ranking + Comparison: run identification, review ranked candidates side-by-side, confirm.

The software proposes ranked candidates; the scientist makes the final call (confirm a match, or mark
the query as a new individual).
"""

from __future__ import annotations

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

from herpetoid.application.identification_runner import Candidate, IdentificationRunner
from herpetoid.gui.state import AppState
from herpetoid.gui.widgets.image_viewer import ImageViewer


def _viewer_panel(title: str) -> tuple[QWidget, ImageViewer]:
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(QLabel(f"<b>{title}</b>"))
    viewer = ImageViewer()
    layout.addWidget(viewer)
    return panel, viewer


class CandidateRankingScreen(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._candidates: list[Candidate] = []
        self._query_observation_id: int | None = None
        self._species_names: dict[int | None, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Query observation:"))
        self.query_combo = QComboBox()
        self.query_combo.setMinimumWidth(260)
        controls.addWidget(self.query_combo, 1)
        controls.addWidget(QLabel("Algorithm:"))
        self.algorithm_combo = QComboBox()
        controls.addWidget(self.algorithm_combo)
        self.identify_button = QPushButton("Identify")
        self.identify_button.setObjectName("primary")
        self.identify_button.clicked.connect(self.identify)
        controls.addWidget(self.identify_button)
        controls.addStretch(1)
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
        query_panel, self.query_viewer = _viewer_panel("Query")
        candidate_panel, self.candidate_viewer = _viewer_panel("Candidate")
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
        self._populate_queries()
        self._populate_algorithms()
        has_project = self._state.project is not None
        for widget in (self.query_combo, self.algorithm_combo, self.identify_button):
            widget.setEnabled(has_project)
        self.status_label.setText("" if has_project else "Open a project first.")
        self._update_action_buttons()

    def _populate_queries(self) -> None:
        self.query_combo.clear()
        catalog = self._state.catalog
        if catalog is None:
            return
        self._species_names = {s.id: s.scientific_name for s in catalog.list_species()}
        for obs in catalog.list_observations():
            species = self._species_names.get(obs.species_id, "")
            self.query_combo.addItem(f"Obs {obs.id} · {species} · {obs.observer or '-'}", obs.id)

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

        self._show_image(self.query_viewer, self._query_observation_id)
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
        self._update_action_buttons()

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
