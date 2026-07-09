"""Comparison window: a direct one-vs-one comparison of any two observations.

Where *Candidates* ranks the whole catalog against a query, this screen answers a focused question:
"are these two the same individual?" It preprocesses both patterns, runs the chosen algorithm and shows
the two normalized ventral patterns side by side with the matched spots joined by lines — the visual
evidence the scientist uses to make the final call.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
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
    query_image: np.ndarray, target_image: np.ndarray, correspondences: np.ndarray | None
) -> np.ndarray:
    """Lay the two patterns side by side and draw a colored line between each matched spot."""
    import cv2

    left = _to_rgb_u8(query_image)
    right = _to_rgb_u8(target_image)
    hl, wl = left.shape[:2]
    hr, wr = right.shape[:2]
    height = max(hl, hr)
    canvas = np.full((height, wl + _GAP + wr, 3), 245, np.uint8)
    canvas[:hl, :wl] = left
    offset = wl + _GAP
    canvas[:hr, offset : offset + wr] = right

    if correspondences is not None and len(correspondences) > 0:
        points = np.rint(np.asarray(correspondences, dtype=float)).astype(int)
        count = len(points)
        hsv = np.zeros((count, 1, 3), np.uint8)
        hsv[:, 0, 0] = (np.arange(count) * 180 // max(1, count)).astype(np.uint8)  # spread hues
        hsv[:, 0, 1] = 200
        hsv[:, 0, 2] = 255
        colors = cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB).reshape(count, 3)
        for (qx, qy, tx, ty), rgb in zip(points, colors, strict=False):
            color = (int(rgb[0]), int(rgb[1]), int(rgb[2]))
            pa = (int(qx), int(qy))
            pb = (int(tx) + offset, int(ty))
            cv2.line(canvas, pa, pb, color, 1, cv2.LINE_AA)
            cv2.circle(canvas, pa, 3, color, -1, cv2.LINE_AA)
            cv2.circle(canvas, pb, 3, color, -1, cv2.LINE_AA)
    return canvas


class ComparisonScreen(QWidget):
    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._comparison: PairwiseComparison | None = None
        self._species_names: dict[int | None, str] = {}

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

        self.result_label = QLabel("Pick two observations and press Compare.")
        self.result_label.setStyleSheet("color: palette(mid);")
        layout.addWidget(self.result_label)

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

    def _refresh(self) -> None:
        self._comparison = None
        self.viewer.clear()
        self._populate_observations()
        self._populate_algorithms()
        has_pair = self.obs_a_combo.count() >= 2
        for widget in (self.obs_a_combo, self.obs_b_combo, self.algorithm_combo):
            widget.setEnabled(self._state.project is not None)
        self.compare_button.setEnabled(has_pair)
        if self._state.project is None:
            self.result_label.setText("Open a project first.")
        elif not has_pair:
            self.result_label.setText("Import at least two observations to compare.")
        else:
            self.result_label.setText("Pick two observations and press Compare.")
            if self.obs_b_combo.count() >= 2:
                self.obs_b_combo.setCurrentIndex(1)  # default to a different second observation

    def _populate_observations(self) -> None:
        self.obs_a_combo.clear()
        self.obs_b_combo.clear()
        catalog = self._state.catalog
        if catalog is None:
            return
        self._species_names = {s.id: s.scientific_name for s in catalog.list_species()}
        for obs in catalog.list_observations():
            species = self._species_names.get(obs.species_id, "")
            label = f"Obs {obs.id} · {species} · {obs.observer or '-'}"
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
            self.result_label.setText("Pick two different observations.")
            self.viewer.clear()
            return

        runner = IdentificationRunner(project, self._state.registry, self._state.identification)
        try:
            comparison = runner.compare(int(a_id), int(b_id), str(algorithm_id))
        except Exception as exc:  # surface any plugin failure without crashing
            self.result_label.setText(f"Comparison failed: {exc}")
            return
        if comparison is None:
            self.result_label.setText("Could not compare these observations.")
            self.viewer.clear()
            return

        self._comparison = comparison
        result = comparison.result
        composite = build_match_composite(
            comparison.query_sample.image,
            comparison.target_sample.image,
            result.correspondences,
        )
        self.viewer.set_image(composite)
        good = int(result.meta.get("good_matches", 0))
        self.result_label.setText(
            f"Similarity {result.normalized_score:.3f}  ·  {result.inliers} inlier matches "
            f"(of {good} good)  ·  inlier ratio {result.inlier_ratio:.2f}"
        )
