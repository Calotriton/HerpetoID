"""Identification: run a query against the catalog, review ranked matches, confirm — or compare A/B.

Merges the former Candidates and Comparison screens. *Identify* mode ranks the catalog against a
query (any observation with a marked ROI, assigned or not) and presents the top matches as cards;
selecting a card computes the pairwise match evidence (inliers, matched spots joined by lines) lazily
and renders it in the overlay viewer. *Compare A/B* mode answers the focused one-vs-one question. The
scientist makes the final call (confirm a match, or mark the query as a new individual).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from herpetoid.application.catalog_service import PENDING_CODE_KEY, pending_code
from herpetoid.application.identification_runner import (
    Candidate,
    IdentificationRunner,
    PairwiseComparison,
)
from herpetoid.gui.state import AppState
from herpetoid.gui.widgets.image_viewer import ndarray_to_qimage
from herpetoid.gui.widgets.info_table import InfoTable
from herpetoid.gui.widgets.match_overlay import MatchOverlayViewer
from herpetoid.gui.widgets.observation_panel import (
    ObservationPanel,
    observation_image_and_roi,
    show_observation_info,
)
from herpetoid.gui.widgets.roi_preview import RoiPreview, roi_crop

_THUMB_W, _THUMB_H = 96, 72


def _score_color(score: float) -> str:
    if score >= 0.5:
        return "#2fae6b"
    if score >= 0.25:
        return "#e0a13a"
    return "#d9534f"


class _CandidateCard(QFrame):
    """One ranked match: rank, individual code, score bar, ROI thumbnail and lazy match detail."""

    def __init__(self, candidate: Candidate, thumbnail: QPixmap | None) -> None:
        super().__init__()
        self.setObjectName("matchCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(10)

        thumb = QLabel()
        thumb.setFixedSize(_THUMB_W, _THUMB_H)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setFrameShape(QFrame.Shape.StyledPanel)
        if thumbnail is not None:
            thumb.setPixmap(
                thumbnail.scaled(
                    thumb.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
        else:
            thumb.setText("No ROI")
        layout.addWidget(thumb)

        body = QVBoxLayout()
        body.setSpacing(3)
        header = QHBoxLayout()
        code = candidate.individual.code if candidate.individual else f"Obs {candidate.observation.id}"
        title = QLabel(f"<b>{candidate.rank}. {code}</b>")
        header.addWidget(title)
        header.addStretch(1)
        color = _score_color(candidate.normalized_score)
        score = QLabel(f"Score: {candidate.normalized_score:.2f}")
        score.setStyleSheet(f"color: {color}; font-weight: 600;")
        header.addWidget(score)
        body.addLayout(header)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(round(candidate.normalized_score * 100))
        bar.setTextVisible(False)
        bar.setFixedHeight(5)
        bar.setStyleSheet(
            "QProgressBar { border: none; background: palette(mid); border-radius: 2px; }"
            f"QProgressBar::chunk {{ background: {color}; border-radius: 2px; }}"
        )
        body.addWidget(bar)

        self.detail_label = QLabel("Select for match details")
        self.detail_label.setStyleSheet("color: palette(mid); font-size: 12px;")
        body.addWidget(self.detail_label)
        layout.addLayout(body, 1)

    def set_detail(self, text: str) -> None:
        self.detail_label.setText(text)


class _FirstIndividualCodeDialog(QDialog):
    """Asks for the first individual's code when none was typed in the Observations editor."""

    def __init__(self, default_code: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Code for the first individual")
        layout = QVBoxLayout(self)
        label = QLabel(
            "No individual code was entered for this observation. Write one now, or keep the "
            "suggested default."
        )
        label.setWordWrap(True)
        layout.addWidget(label)
        self.code_edit = QLineEdit(default_code)
        self.code_edit.selectAll()
        layout.addWidget(self.code_edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def code(self) -> str:
        return self.code_edit.text().strip()


class IdentificationScreen(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._candidates: list[Candidate] = []
        self._query_observation_id: int | None = None
        self._first_dialog: QMessageBox | None = None
        self._first_mark_button: QPushButton | None = None
        self._first_code_dialog: _FirstIndividualCodeDialog | None = None
        self._top_k: int = 0
        self._pair_cache: dict[int, PairwiseComparison] = {}
        self._species_names: dict[int | None, str] = {}
        self._species_by_obs: dict[int | None, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        layout.addLayout(self._build_controls())
        layout.addWidget(self._build_body(), 1)
        layout.addLayout(self._build_actions())

        state.project_changed.connect(self._refresh)
        self._refresh()

    # -- construction ------------------------------------------------------------------------------
    def _build_controls(self) -> QHBoxLayout:
        controls = QHBoxLayout()

        # The mode switch is a compact segmented toggle (styled via #modeSwitch) so it cannot be
        # mistaken for the primary "Run …" action button on the right.
        mode_label = QLabel("Mode:")
        mode_label.setStyleSheet("color: palette(mid);")
        controls.addWidget(mode_label)
        self.identify_mode_button = QPushButton("Identification")
        self.identify_mode_button.setCheckable(True)
        self.identify_mode_button.setChecked(True)
        self.compare_mode_button = QPushButton("Compare A/B")
        self.compare_mode_button.setCheckable(True)
        for button in (self.identify_mode_button, self.compare_mode_button):
            button.setObjectName("modeSwitch")
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.identify_mode_button)
        group.addButton(self.compare_mode_button)
        self.identify_mode_button.clicked.connect(lambda: self.set_mode("identify"))
        self.compare_mode_button.clicked.connect(lambda: self.set_mode("compare"))
        controls.addWidget(self.identify_mode_button)
        controls.addWidget(self.compare_mode_button)
        controls.addSpacing(18)

        self._control_stack = QStackedWidget()

        identify_row = QWidget()
        identify_layout = QHBoxLayout(identify_row)
        identify_layout.setContentsMargins(0, 0, 0, 0)
        identify_layout.addWidget(QLabel("<b>Query:</b>"))
        self.query_combo = QComboBox()
        self.query_combo.setMinimumWidth(170)
        self.query_combo.currentIndexChanged.connect(self._on_query_changed)
        identify_layout.addWidget(self.query_combo)
        self.query_species_label = QLabel()
        self.query_species_label.setStyleSheet("color: palette(mid);")
        identify_layout.addWidget(self.query_species_label)
        identify_layout.addStretch(1)
        self.identify_button = QPushButton("Run identification")
        self.identify_button.setObjectName("primary")
        self.identify_button.clicked.connect(self.identify)
        identify_layout.addWidget(self.identify_button)
        self._control_stack.addWidget(identify_row)

        compare_row = QWidget()
        compare_layout = QHBoxLayout(compare_row)
        compare_layout.setContentsMargins(0, 0, 0, 0)
        compare_layout.addWidget(QLabel("<b>A:</b>"))
        self.obs_a_combo = QComboBox()
        self.obs_a_combo.setMinimumWidth(140)
        compare_layout.addWidget(self.obs_a_combo)
        compare_layout.addWidget(QLabel("<b>B:</b>"))
        self.obs_b_combo = QComboBox()
        self.obs_b_combo.setMinimumWidth(140)
        compare_layout.addWidget(self.obs_b_combo)
        self.species_label = QLabel()
        self.species_label.setStyleSheet("color: palette(mid);")
        compare_layout.addWidget(self.species_label)
        compare_layout.addStretch(1)
        self.compare_button = QPushButton("Run comparison")
        self.compare_button.setObjectName("primary")
        self.compare_button.clicked.connect(self.compare)
        compare_layout.addWidget(self.compare_button)
        self._control_stack.addWidget(compare_row)
        self.obs_a_combo.currentIndexChanged.connect(self._on_compare_a_changed)
        self.obs_b_combo.currentIndexChanged.connect(self._update_species_label)

        controls.addWidget(self._control_stack, 1)
        controls.addSpacing(14)
        controls.addWidget(QLabel("Algorithm:"))
        self.algorithm_combo = QComboBox()
        controls.addWidget(self.algorithm_combo)
        return controls

    def _build_body(self) -> QSplitter:
        splitter = QSplitter(Qt.Orientation.Horizontal)

        self.query_panel = ObservationPanel("Query observation")
        splitter.addWidget(self.query_panel)

        self._matches_panel = QWidget()
        matches_layout = QVBoxLayout(self._matches_panel)
        matches_layout.setContentsMargins(0, 0, 0, 0)
        matches_layout.addWidget(QLabel("<b>Top matches</b>"))
        self.cards = QListWidget()
        self.cards.setObjectName("matchCards")
        self.cards.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.cards.currentRowChanged.connect(self._on_candidate_select)
        matches_layout.addWidget(self.cards, 1)
        self.show_more_button = QPushButton("Show more candidates")
        self.show_more_button.clicked.connect(self.show_more)
        matches_layout.addWidget(self.show_more_button)
        self._matches_panel.setMinimumWidth(280)
        self._matches_panel.setMaximumWidth(380)
        splitter.addWidget(self._matches_panel)

        detail_panel = QWidget()
        detail_layout = QVBoxLayout(detail_panel)
        detail_layout.setContentsMargins(0, 0, 0, 0)
        self.overlay = MatchOverlayViewer()
        detail_layout.addWidget(self.overlay, 3)
        candidate_row = QHBoxLayout()
        self.candidate_info = InfoTable()
        candidate_row.addWidget(self.candidate_info, 1)
        roi_box = QVBoxLayout()
        roi_box.addWidget(QLabel("ROI"))
        self.candidate_roi = RoiPreview()
        roi_box.addWidget(self.candidate_roi)
        roi_box.addStretch(1)
        candidate_row.addLayout(roi_box)
        detail_layout.addLayout(candidate_row, 1)
        splitter.addWidget(detail_panel)

        splitter.setStretchFactor(0, 2)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 3)
        splitter.setSizes([360, 300, 560])
        return splitter

    def _build_actions(self) -> QHBoxLayout:
        actions = QHBoxLayout()
        self.status_label = QLabel()
        actions.addWidget(self.status_label)
        actions.addStretch(1)
        self._decision_label = QLabel("Your decision:")
        self._decision_label.setStyleSheet("color: palette(mid);")
        actions.addWidget(self._decision_label)
        # Two equally visible verdicts: "new individual" is an accent outline, "same individual" is
        # the filled primary — clearly siblings, clearly different outcomes.
        self.new_button = QPushButton("✚ Mark query as NEW individual")
        self.new_button.setObjectName("accentOutline")
        self.new_button.clicked.connect(self.mark_new)
        self.confirm_button = QPushButton("✓ Confirm SAME individual as match")
        self.confirm_button.setObjectName("primary")
        self.confirm_button.clicked.connect(self.confirm_same)
        actions.addWidget(self.new_button)
        actions.addWidget(self.confirm_button)
        return actions

    # -- modes -------------------------------------------------------------------------------------
    def mode(self) -> str:
        return "compare" if self.compare_mode_button.isChecked() else "identify"

    def set_mode(self, mode: str) -> None:
        compare = mode == "compare"
        self.compare_mode_button.setChecked(compare)
        self.identify_mode_button.setChecked(not compare)
        self._control_stack.setCurrentIndex(1 if compare else 0)
        self._matches_panel.setVisible(not compare)
        self._decision_label.setVisible(not compare)
        self.new_button.setVisible(not compare)
        self.confirm_button.setVisible(not compare)
        self.query_panel.title_label.setText(
            "<b>Observation A</b>" if compare else "<b>Query observation</b>"
        )
        if compare:
            self._on_compare_a_changed()
        else:
            self._on_query_changed()

    # -- state -------------------------------------------------------------------------------------
    def _refresh(self) -> None:
        self._candidates = []
        self._query_observation_id = None
        self._pair_cache.clear()
        self.cards.clear()
        self.query_panel.clear()
        self.candidate_info.clear_rows()
        self.candidate_roi.clear_preview()
        self.overlay.clear()
        self._populate_observations()
        self._populate_algorithms()
        has_project = self._state.project is not None
        has_queries = self.query_combo.count() > 0
        for widget in (self.query_combo, self.algorithm_combo, self.identify_button):
            widget.setEnabled(has_project and has_queries)
        for widget in (self.obs_a_combo, self.obs_b_combo):
            widget.setEnabled(has_project)
        self.compare_button.setEnabled(self.obs_a_combo.count() >= 2)
        self.show_more_button.setEnabled(False)
        if not has_project:
            self.status_label.setText("Open a project first.")
        elif not has_queries:
            self.status_label.setText(
                "Nothing to identify yet — mark a ROI on an observation (Observations tab) first."
            )
        else:
            self.status_label.setText("")
        if self.obs_b_combo.count() >= 2:
            self.obs_b_combo.setCurrentIndex(1)  # default to a different second observation
        self._update_action_buttons()

    def _populate_observations(self) -> None:
        self.query_combo.clear()
        self.obs_a_combo.clear()
        self.obs_b_combo.clear()
        catalog = self._state.catalog
        if catalog is None:
            return
        self._species_names = {s.id: s.scientific_name for s in catalog.list_species()}
        self._species_by_obs = {}
        codes = {i.id: i.code for i in catalog.list_individuals()}
        # Any observation with a marked ROI can be identified (assigned or not). The dropdowns show
        # just the code (the species is shown once, next to them, to avoid repeating it per row).
        for obs in catalog.comparable_observations():
            code = codes.get(obs.individual_id) if obs.individual_id else None
            if code is None and (pending := pending_code(obs)):
                label = f"Obs {obs.id} · {pending} (pending)"
            else:
                label = code if code else f"Obs {obs.id} (unassigned)"
            self.query_combo.addItem(label, obs.id)
            self.obs_a_combo.addItem(label, obs.id)
            self.obs_b_combo.addItem(label, obs.id)
            self._species_by_obs[obs.id] = self._species_names.get(obs.species_id, "")
        self._on_query_changed()
        self._update_species_label()

    def _update_query_species(self) -> None:
        obs_id = self.query_combo.currentData()
        species = self._species_by_obs.get(obs_id, "") if obs_id is not None else ""
        self.query_species_label.setText(f"Species: {species}" if species else "")

    def _on_query_changed(self) -> None:
        """Show the picked query immediately, so it is visible before running anything."""
        self._update_query_species()
        if self.mode() == "identify":
            obs_id = self.query_combo.currentData()
            self.query_panel.show_observation(
                self._state, int(obs_id) if obs_id is not None else None
            )

    def _on_compare_a_changed(self) -> None:
        self._update_species_label()
        if self.mode() == "compare":
            obs_id = self.obs_a_combo.currentData()
            self.query_panel.show_observation(
                self._state, int(obs_id) if obs_id is not None else None
            )

    def _update_species_label(self) -> None:
        a_species = self._species_by_obs.get(self.obs_a_combo.currentData(), "")
        b_species = self._species_by_obs.get(self.obs_b_combo.currentData(), "")
        if a_species and a_species == b_species:
            self.species_label.setText(f"Species: {a_species}")
        elif a_species or b_species:
            self.species_label.setText(f"Species: A {a_species or '—'} · B {b_species or '—'}")
        else:
            self.species_label.setText("")

    def _populate_algorithms(self) -> None:
        self.algorithm_combo.clear()
        for record in self._state.registry.algorithms(enabled_only=True):
            self.algorithm_combo.addItem(record.descriptor.name, record.descriptor.algorithm_id)
        default = self._state.default_algorithm_id
        if default is not None:
            index = self.algorithm_combo.findData(default)
            if index >= 0:
                self.algorithm_combo.setCurrentIndex(index)

    # -- identify ----------------------------------------------------------------------------------
    def identify(self) -> None:
        self._top_k = self._state.settings.settings.default_top_k
        self._run_identify()

    def show_more(self) -> None:
        if self._query_observation_id is None:
            return
        self._top_k += self._state.settings.settings.default_top_k
        self._run_identify()

    def _run_identify(self) -> None:
        project = self._state.project
        query_id = self.query_combo.currentData()
        algorithm_id = self.algorithm_combo.currentData()
        if project is None or query_id is None or algorithm_id is None:
            return
        if self._query_observation_id != int(query_id):
            self._pair_cache.clear()
        self._query_observation_id = int(query_id)
        runner = IdentificationRunner(project, self._state.registry, self._state.identification)
        try:
            self._candidates = runner.identify(
                int(query_id), str(algorithm_id), top_k=self._top_k
            )
        except Exception as exc:  # surface any plugin failure without crashing
            self.status_label.setText(f"Identification failed: {exc}")
            return

        # Record that this observation was actually run through identification (drives the
        # Observations "Ident." column) — distinct from merely having an individual code assigned.
        catalog = self._state.catalog
        if catalog is not None:
            catalog.record_identification(self._query_observation_id, str(algorithm_id))

        self.query_panel.show_observation(self._state, self._query_observation_id)
        self.candidate_info.clear_rows()
        self.candidate_roi.clear_preview()
        self.overlay.clear()
        self.cards.blockSignals(True)
        self.cards.clear()
        for candidate in self._candidates:
            card = _CandidateCard(candidate, self._thumbnail_for(candidate))
            item = QListWidgetItem()
            item.setSizeHint(card.sizeHint())
            self.cards.addItem(item)
            self.cards.setItemWidget(item, card)
        self.cards.blockSignals(False)
        # More candidates may exist only if this run filled the requested top-k.
        self.show_more_button.setEnabled(len(self._candidates) >= self._top_k)
        if self._candidates:
            self.cards.setCurrentRow(0)
        self.status_label.setText(
            f"{len(self._candidates)} candidate(s) — the final decision is yours."
            if self._candidates
            else "No other observations to compare against yet."
        )
        self._update_action_buttons()
        if not self._candidates:
            self._maybe_offer_first_individual()

    def _thumbnail_for(self, candidate: Candidate) -> QPixmap | None:
        if candidate.observation.id is None:
            return None
        image, roi = observation_image_and_roi(self._state, candidate.observation.id)
        crop = roi_crop(image, roi)
        if crop is None:
            return None
        return QPixmap.fromImage(ndarray_to_qimage(crop))

    def select_candidate(self, row: int) -> None:
        self.cards.setCurrentRow(row)

    def _on_candidate_select(self) -> None:
        candidate = self._selected_candidate()
        if candidate is not None and candidate.observation.id is not None:
            code = candidate.individual.code if candidate.individual is not None else None
            show_observation_info(
                self._state,
                self.candidate_info,
                self.candidate_roi,
                candidate.observation.id,
                individual_code=code,
            )
            self._show_match_evidence(candidate)
        self._update_action_buttons()

    def _show_match_evidence(self, candidate: Candidate) -> None:
        """Compute (lazily, cached per pair) and render the pairwise match for the selected card."""
        project = self._state.project
        algorithm_id = self.algorithm_combo.currentData()
        query_id = self._query_observation_id
        obs_id = candidate.observation.id
        if project is None or algorithm_id is None or query_id is None or obs_id is None:
            return
        comparison = self._pair_cache.get(obs_id)
        if comparison is None:
            runner = IdentificationRunner(
                project, self._state.registry, self._state.identification
            )
            try:
                comparison = runner.compare(query_id, obs_id, str(algorithm_id))
            except Exception as exc:  # surface any plugin failure without crashing
                self.overlay.clear()
                self.overlay.set_status(f"Match rendering failed: {exc}")
                return
            if comparison is None:
                self.overlay.clear()
                self.overlay.set_status("Could not compute the match for this pair.")
                return
            self._pair_cache[obs_id] = comparison
        self.overlay.show_comparison(comparison)
        card = self.cards.itemWidget(self.cards.currentItem())
        if isinstance(card, _CandidateCard):
            result = comparison.result
            good = int(result.meta.get("good_matches", 0))
            card.set_detail(
                f"{result.inliers} inliers of {good} good · ratio {result.inlier_ratio:.2f}"
            )

    def _selected_candidate(self) -> Candidate | None:
        row = self.cards.currentRow()
        return self._candidates[row] if 0 <= row < len(self._candidates) else None

    def _update_action_buttons(self) -> None:
        has_query = self._query_observation_id is not None
        self.confirm_button.setEnabled(has_query and self._selected_candidate() is not None)
        self.new_button.setEnabled(has_query)

    # -- confirm -----------------------------------------------------------------------------------
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
        self._clear_pending_code(self._query_observation_id)  # superseded by the confirmed match
        self.status_label.setText(f"Linked to individual {code}.")
        self._state.project_changed.emit()

    def mark_new(self) -> None:
        """Confirm the query as a new individual — this is where individuals are actually created.

        Reuses the code the user typed in the Observations editor (kept *pending* until now); if the
        query is already assigned, it does nothing rather than minting a duplicate individual.
        """
        self._assign_query_as_new()

    def _assign_query_as_new(self, code_override: str | None = None, *, first: bool = False) -> None:
        catalog = self._state.catalog
        if catalog is None or self._query_observation_id is None:
            return
        query = catalog.get_observation(self._query_observation_id)
        if query is None:
            return
        if query.individual_id is not None:
            existing = catalog.get_individual(query.individual_id)
            code = existing.code if existing is not None else "?"
            self.status_label.setText(f"Already assigned to individual {code}.")
            return
        code_hint = code_override or pending_code(query)
        if code_hint:
            individual = catalog.find_individual_by_code(
                query.species_id, code_hint
            ) or catalog.create_individual(query.species_id, code=code_hint)
        else:
            individual = catalog.create_individual(query.species_id)
        catalog.link_observation(self._query_observation_id, individual.id)
        self._clear_pending_code(self._query_observation_id)
        # Emit first: the refresh it triggers resets the status label, and this outcome must stay
        # visible afterwards.
        self._state.project_changed.emit()
        self.status_label.setText(
            f"Marked as the first individual of the project: {individual.code}."
            if first
            else f"Created individual {individual.code}."
        )

    # -- first individual of the project -------------------------------------------------------------
    def _maybe_offer_first_individual(self) -> None:
        """Offer to enrol the query as the project's first individual.

        Shown when an identification run yields no candidates because the catalog holds no
        individuals yet — otherwise it looks like "nothing happened". Non-modal (``open()``) so the
        workflow keeps updating live and headless test drivers are not blocked.
        """
        catalog = self._state.catalog
        query_id = self._query_observation_id
        if catalog is None or query_id is None or catalog.individual_count() > 0:
            return
        query = catalog.get_observation(query_id)
        if query is None or query.individual_id is not None:
            return
        box = QMessageBox(self)
        box.setWindowTitle("First individual of the project")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(
            "There are no cataloged individuals to compare against yet — this appears to be the "
            "first individual of the project."
        )
        box.setInformativeText("Mark it as the first individual, or cancel to go back.")
        self._first_mark_button = box.addButton(
            "Mark as first individual", QMessageBox.ButtonRole.AcceptRole
        )
        box.addButton(QMessageBox.StandardButton.Cancel)
        box.buttonClicked.connect(self._on_first_dialog_clicked)
        self._first_dialog = box
        self.status_label.setText(
            "No previous captures to compare against — the first individual of the project?"
        )
        box.open()

    def _on_first_dialog_clicked(self, button: QAbstractButton) -> None:
        if button is not self._first_mark_button:
            return
        catalog = self._state.catalog
        query_id = self._query_observation_id
        if catalog is None or query_id is None:
            return
        query = catalog.get_observation(query_id)
        if query is None:
            return
        code = pending_code(query)
        if code:
            # A non-default code was already entered in the Observations editor — use it.
            self._assign_query_as_new(code, first=True)
            return
        dialog = _FirstIndividualCodeDialog("IND-001", self)
        dialog.accepted.connect(
            lambda: self._assign_query_as_new(dialog.code() or None, first=True)
        )
        self._first_code_dialog = dialog
        dialog.open()

    def _clear_pending_code(self, observation_id: int) -> None:
        catalog = self._state.catalog
        if catalog is None:
            return
        observation = catalog.get_observation(observation_id)
        if observation is None or PENDING_CODE_KEY not in observation.measurements:
            return
        observation.measurements.pop(PENDING_CODE_KEY)
        catalog.update_observation(observation)

    # -- compare A/B -------------------------------------------------------------------------------
    def compare(self) -> None:
        project = self._state.project
        a_id = self.obs_a_combo.currentData()
        b_id = self.obs_b_combo.currentData()
        algorithm_id = self.algorithm_combo.currentData()
        if project is None or a_id is None or b_id is None or algorithm_id is None:
            return
        if a_id == b_id:
            self.overlay.clear()
            self.overlay.set_status("Pick two different observations.")
            return

        runner = IdentificationRunner(project, self._state.registry, self._state.identification)
        try:
            comparison = runner.compare(int(a_id), int(b_id), str(algorithm_id))
        except Exception as exc:  # surface any plugin failure without crashing
            self.overlay.set_status(f"Comparison failed: {exc}")
            return
        if comparison is None:
            self.overlay.clear()
            self.overlay.set_status("Could not compare these observations.")
            return

        self.query_panel.show_observation(self._state, int(a_id))
        show_observation_info(self._state, self.candidate_info, self.candidate_roi, int(b_id))
        self.overlay.show_comparison(comparison)

    @property
    def _comparison(self) -> PairwiseComparison | None:
        return self.overlay.comparison()
