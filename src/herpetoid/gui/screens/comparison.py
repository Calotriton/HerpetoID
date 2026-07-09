"""Comparison window: a direct one-vs-one comparison of any two observations.

Where *Candidates* ranks the whole catalog against a query, this screen answers a focused question:
"are these two the same individual?" It preprocesses both patterns, runs the chosen algorithm and shows
the two normalized ventral patterns side by side with the matched spots joined by lines — the visual
evidence the scientist uses to make the final call. The match overlay is adjustable (hide it, fade it,
or show only the strongest N lines) so a human can inspect the patterns underneath.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from herpetoid.application.identification_runner import IdentificationRunner, PairwiseComparison
from herpetoid.gui.state import AppState
from herpetoid.gui.widgets.image_viewer import ImageViewer

_GAP = 24  # pixels between the two patterns in the composite


def _to_rgb_u8(image: np.ndarray) -> np.ndarray:
    array = np.asarray(image)
    if array.dtype != np.uint8:
        values = array.astype(np.float64)
        low, high = float(values.min()), float(values.max())
        array = (
            np.zeros(array.shape, np.uint8)
            if high <= low
            else ((values - low) / (high - low) * 255.0).astype(np.uint8)
        )
    if array.ndim == 2:
        array = np.stack([array] * 3, axis=-1)
    elif array.shape[2] == 4:
        array = array[:, :, :3]
    return np.ascontiguousarray(array)


def build_match_composite(
    query_image: np.ndarray,
    target_image: np.ndarray,
    correspondences: np.ndarray | None,
    *,
    show_lines: bool = True,
    show_points: bool = True,
    max_matches: int | None = None,
    opacity: float = 1.0,
) -> np.ndarray:
    """Lay the two patterns side by side and draw the matched spots.

    ``max_matches`` limits how many correspondences are drawn, ``opacity`` (0-1) fades the overlay so
    the patterns stay visible underneath, and ``show_lines`` / ``show_points`` toggle each layer.
    """
    import cv2

    left = _to_rgb_u8(query_image)
    right = _to_rgb_u8(target_image)
    hl, wl = left.shape[:2]
    hr, wr = right.shape[:2]
    height = max(hl, hr)
    base = np.full((height, wl + _GAP + wr, 3), 245, np.uint8)
    base[:hl, :wl] = left
    offset = wl + _GAP
    base[:hr, offset : offset + wr] = right

    has_matches = correspondences is not None and len(correspondences) > 0
    if not has_matches or opacity <= 0 or not (show_lines or show_points):
        return base

    points = np.rint(np.asarray(correspondences, dtype=float)).astype(int)
    if max_matches is not None:
        points = points[: max(0, max_matches)]
    count = len(points)
    if count == 0:
        return base

    hsv = np.zeros((count, 1, 3), np.uint8)
    hsv[:, 0, 0] = (np.arange(count) * 180 // max(1, count)).astype(np.uint8)  # spread hues
    hsv[:, 0, 1] = 200
    hsv[:, 0, 2] = 255
    colors = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB).reshape(count, 3)

    overlay = base.copy()
    for (qx, qy, tx, ty), rgb in zip(points, colors, strict=False):
        color = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
        pa = (int(qx), int(qy))
        pb = (int(tx) + offset, int(ty))
        if show_lines:
            cv2.line(overlay, pa, pb, color, 1, cv2.LINE_AA)
        if show_points:
            cv2.circle(overlay, pa, 3, color, -1, cv2.LINE_AA)
            cv2.circle(overlay, pb, 3, color, -1, cv2.LINE_AA)

    alpha = float(min(1.0, max(0.0, opacity)))
    if alpha >= 1.0:
        return overlay
    return cv2.addWeighted(overlay, alpha, base, 1.0 - alpha, 0.0)


class ComparisonScreen(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._comparison: PairwiseComparison | None = None
        self._species_names: dict[int | None, str] = {}
        self._composite_shape: tuple[int, ...] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("Compare two observations")
        title.setStyleSheet("font-size: 18px; font-weight: 700;")
        layout.addWidget(title)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Observation A"))
        self.obs_a_combo = QComboBox()
        self.obs_a_combo.setMinimumWidth(220)
        controls.addWidget(self.obs_a_combo)
        controls.addWidget(QLabel("Observation B"))
        self.obs_b_combo = QComboBox()
        self.obs_b_combo.setMinimumWidth(220)
        controls.addWidget(self.obs_b_combo)
        controls.addWidget(QLabel("Algorithm"))
        self.algorithm_combo = QComboBox()
        controls.addWidget(self.algorithm_combo)
        self.compare_button = QPushButton("Compare")
        self.compare_button.setObjectName("primary")
        self.compare_button.clicked.connect(self.compare)
        controls.addWidget(self.compare_button)
        controls.addStretch(1)
        layout.addLayout(controls)

        layout.addWidget(self._build_result_panel())
        layout.addWidget(self._build_overlay_controls())

        self.viewer = ImageViewer()
        layout.addWidget(self.viewer, 1)

        hint = QLabel(
            "Each line joins a matched pattern feature. Many consistent lines suggest the same "
            "individual; few or scattered lines suggest different individuals."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(mid); font-size: 12px;")
        layout.addWidget(hint)

        state.project_changed.connect(self._refresh)
        self._refresh()

    # -- construction helpers --------------------------------------------------------------------
    def _build_result_panel(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("resultPanel")
        panel.setStyleSheet(
            "#resultPanel { border: 1px solid palette(mid); border-radius: 10px; }"
        )
        panel_layout = QHBoxLayout(panel)
        panel_layout.setContentsMargins(16, 10, 16, 10)

        score_box = QVBoxLayout()
        score_box.setSpacing(0)
        self.score_label = QLabel("—")
        self.score_label.setStyleSheet("font-size: 34px; font-weight: 800;")
        caption = QLabel("SIMILARITY")
        caption.setStyleSheet("font-size: 10px; letter-spacing: 1px; color: palette(mid);")
        score_box.addWidget(self.score_label)
        score_box.addWidget(caption)
        panel_layout.addLayout(score_box)

        self.verdict_label = QLabel("")
        self.verdict_label.setStyleSheet("font-size: 15px; font-weight: 600;")
        panel_layout.addSpacing(14)
        panel_layout.addWidget(self.verdict_label)
        panel_layout.addStretch(1)

        self.detail_label = QLabel("Pick two observations and press Compare.")
        self.detail_label.setStyleSheet("color: palette(mid);")
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        panel_layout.addWidget(self.detail_label)
        return panel

    def _build_overlay_controls(self) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(2, 0, 2, 0)

        self.lines_check = QCheckBox("Match lines")
        self.lines_check.setChecked(True)
        self.lines_check.toggled.connect(self._render_composite)
        self.points_check = QCheckBox("Points")
        self.points_check.setChecked(True)
        self.points_check.toggled.connect(self._render_composite)
        row_layout.addWidget(self.lines_check)
        row_layout.addWidget(self.points_check)

        row_layout.addSpacing(16)
        row_layout.addWidget(QLabel("Show up to"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(0, 0)
        self.count_spin.setSuffix(" lines")
        self.count_spin.valueChanged.connect(self._render_composite)
        row_layout.addWidget(self.count_spin)

        row_layout.addSpacing(16)
        row_layout.addWidget(QLabel("Opacity"))
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(10, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.setFixedWidth(140)
        self.opacity_slider.valueChanged.connect(self._render_composite)
        row_layout.addWidget(self.opacity_slider)
        row_layout.addStretch(1)

        self._overlay_controls = (
            self.lines_check,
            self.points_check,
            self.count_spin,
            self.opacity_slider,
        )
        self._set_overlay_controls_enabled(False)
        return row

    # -- state -----------------------------------------------------------------------------------
    def _refresh(self) -> None:
        self._comparison = None
        self._composite_shape = None
        self.viewer.clear()
        self._reset_result_panel()
        self._set_overlay_controls_enabled(False)
        self._populate_observations()
        self._populate_algorithms()
        has_pair = self.obs_a_combo.count() >= 2
        for widget in (self.obs_a_combo, self.obs_b_combo, self.algorithm_combo):
            widget.setEnabled(self._state.project is not None)
        self.compare_button.setEnabled(has_pair)
        if self._state.project is None:
            self.detail_label.setText("Open a project first.")
        elif not has_pair:
            self.detail_label.setText(
                "Need at least two observations with a marked ROI (Observations tab) to compare."
            )
        else:
            self.detail_label.setText("Pick two observations and press Compare.")
            if self.obs_b_combo.count() >= 2:
                self.obs_b_combo.setCurrentIndex(1)  # default to a different second observation

    def _populate_observations(self) -> None:
        self.obs_a_combo.clear()
        self.obs_b_combo.clear()
        catalog = self._state.catalog
        if catalog is None:
            return
        self._species_names = {s.id: s.scientific_name for s in catalog.list_species()}
        codes = {i.id: i.code for i in catalog.list_individuals()}
        # Any observation with a marked ROI can be compared (assigned to an individual or not).
        for obs in catalog.comparable_observations():
            species = self._species_names.get(obs.species_id, "")
            code = codes.get(obs.individual_id) if obs.individual_id else None
            label = f"{code} · {species}" if code else f"Obs {obs.id} · {species} · unassigned"
            self.obs_a_combo.addItem(label, obs.id)
            self.obs_b_combo.addItem(label, obs.id)

    def _populate_algorithms(self) -> None:
        self.algorithm_combo.clear()
        for record in self._state.registry.algorithms(enabled_only=True):
            self.algorithm_combo.addItem(record.descriptor.name, record.descriptor.algorithm_id)

    def compare(self) -> None:
        project = self._state.project
        a_id = self.obs_a_combo.currentData()
        b_id = self.obs_b_combo.currentData()
        algorithm_id = self.algorithm_combo.currentData()
        if project is None or a_id is None or b_id is None or algorithm_id is None:
            return
        if a_id == b_id:
            self._reset_result_panel()
            self.detail_label.setText("Pick two different observations.")
            self.viewer.clear()
            self._set_overlay_controls_enabled(False)
            return

        runner = IdentificationRunner(project, self._state.registry, self._state.identification)
        try:
            comparison = runner.compare(int(a_id), int(b_id), str(algorithm_id))
        except Exception as exc:  # surface any plugin failure without crashing
            self.detail_label.setText(f"Comparison failed: {exc}")
            return
        if comparison is None:
            self._reset_result_panel()
            self.detail_label.setText("Could not compare these observations.")
            self.viewer.clear()
            self._set_overlay_controls_enabled(False)
            return

        self._comparison = comparison
        self._composite_shape = None
        self._update_result_panel(comparison)
        total = self._match_count(comparison)
        has_matches = total > 0
        self._set_overlay_controls_enabled(has_matches)
        self.count_spin.blockSignals(True)
        self.count_spin.setRange(0, total)
        self.count_spin.setValue(total)  # show all matches by default
        self.count_spin.blockSignals(False)
        self._render_composite()

    # -- rendering -------------------------------------------------------------------------------
    def _match_count(self, comparison: PairwiseComparison) -> int:
        corr = comparison.result.correspondences
        return 0 if corr is None else len(corr)

    def _render_composite(self) -> None:
        comparison = self._comparison
        if comparison is None:
            return
        composite = build_match_composite(
            comparison.query_sample.image,
            comparison.target_sample.image,
            comparison.result.correspondences,
            show_lines=self.lines_check.isChecked(),
            show_points=self.points_check.isChecked(),
            max_matches=self.count_spin.value(),
            opacity=self.opacity_slider.value() / 100.0,
        )
        # Preserve the user's zoom/rotation across overlay tweaks (the composite size is unchanged).
        keep = self.viewer.has_image() and self._composite_shape == composite.shape
        transform = self.viewer.transform() if keep else None
        self.viewer.set_image(composite)
        if transform is not None:
            self.viewer.setTransform(transform)
        self._composite_shape = composite.shape

    # -- result panel ----------------------------------------------------------------------------
    def _reset_result_panel(self) -> None:
        self.score_label.setText("—")
        self.score_label.setStyleSheet("font-size: 34px; font-weight: 800;")
        self.verdict_label.setText("")
        self.detail_label.setText("")

    def _update_result_panel(self, comparison: PairwiseComparison) -> None:
        result = comparison.result
        score = float(result.normalized_score)
        if score >= 0.5:
            color, verdict = "#2fae6b", "Strong match — likely the same individual"
        elif score >= 0.25:
            color, verdict = "#e0a13a", "Moderate — inspect the pattern carefully"
        else:
            color, verdict = "#d9534f", "Weak — likely different individuals"
        self.score_label.setText(f"{score * 100:.0f}%")
        self.score_label.setStyleSheet(f"font-size: 34px; font-weight: 800; color: {color};")
        self.verdict_label.setText(verdict)
        self.verdict_label.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {color};")
        good = int(result.meta.get("good_matches", 0))
        self.detail_label.setText(
            f"{result.inliers} inlier matches of {good} good\ninlier ratio {result.inlier_ratio:.2f}"
        )

    # -- helpers ---------------------------------------------------------------------------------
    def _set_overlay_controls_enabled(self, enabled: bool) -> None:
        for widget in self._overlay_controls:
            widget.setEnabled(enabled)
