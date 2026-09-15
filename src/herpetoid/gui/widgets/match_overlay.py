"""Match-evidence rendering shared by the identification views.

``build_match_composite`` lays two normalized patterns side by side -- each in its own panel,
on the surrounding background -- with the matched spots joined by colored lines. :class:`MatchOverlayViewer` wraps that composite in a self-contained widget: a result
panel (similarity % + verdict), the overlay controls (hide lines/points, limit N, opacity) and the
image viewer, re-rendering overlay tweaks without re-running the match and preserving the zoom.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QAction, QPalette
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from herpetoid.api import ROI
from herpetoid.application.identification_runner import PairwiseComparison
from herpetoid.gui.widgets.image_viewer import ImageViewer

_GAP = 24  # pixels between the two panels in the composite
#: Fallback panel background when no palette colour is given (a plain light surface).
_BACKGROUND = (245, 245, 245)


@dataclass(eq=False, slots=True)
class SourceImage:
    """One side of a comparison: what it is called, and the photograph it was derived from."""

    title: str
    image: np.ndarray | None = None
    roi: ROI | None = None


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
    background: tuple[int, int, int] = _BACKGROUND,
    frame: tuple[int, int, int] | None = None,
) -> np.ndarray:
    """Lay the two patterns side by side — both upright and at the same height — and draw the matches.

    Each pattern is rotated to portrait if it comes in landscape and scaled to a shared height, so the
    two bellies always read as a like-for-like pair; the correspondence points are mapped through the
    same rotation/scale. ``max_matches`` limits how many correspondences are drawn, ``opacity`` (0-1)
    fades the overlay so the patterns stay visible underneath, and ``show_lines`` / ``show_points``
    toggle each layer.

    Each pattern gets a **panel of its own**, both the same width, centred, painted on
    ``background`` and outlined in ``frame`` -- so the pair reads as two separate spaces on the
    application's own surface rather than two pictures butted together in a slab. Pass the
    surrounding widget's palette colours and the composite disappears into the interface.
    """
    import cv2

    def prepare(image: np.ndarray) -> tuple[np.ndarray, bool, int]:
        """RGB, rotated-to-portrait flag, and the pre-rotation height (for point mapping)."""
        rgb = _to_rgb_u8(image)
        pre_height = rgb.shape[0]
        rotated = rgb.shape[1] > rgb.shape[0]
        if rotated:
            rgb = cv2.rotate(rgb, cv2.ROTATE_90_CLOCKWISE)
        return rgb, rotated, pre_height

    left, left_rotated, left_pre_height = prepare(query_image)
    right, right_rotated, right_pre_height = prepare(target_image)
    height = max(left.shape[0], right.shape[0])
    left_scale = height / left.shape[0]
    right_scale = height / right.shape[0]
    if left_scale != 1.0:
        left = cv2.resize(left, (max(1, round(left.shape[1] * left_scale)), height))
    if right_scale != 1.0:
        right = cv2.resize(right, (max(1, round(right.shape[1] * right_scale)), height))
    wl, wr = left.shape[1], right.shape[1]
    # One panel width for both, each pattern centred in its own: a narrow pattern beside a
    # wide one still reads as an equal pair, and the two captions below line up with them.
    panel = max(wl, wr)
    left_pad, right_pad = (panel - wl) // 2, (panel - wr) // 2
    offset = panel + _GAP
    base = np.full((height, 2 * panel + _GAP, 3), background, np.uint8)
    base[:, left_pad : left_pad + wl] = left
    base[:, offset + right_pad : offset + right_pad + wr] = right
    if frame is not None:
        for x0 in (0, offset):
            # Not antialiased: a 1px axis-aligned rule only blurs, and the bleed would smear
            # the panel edge into the background between them.
            cv2.rectangle(base, (x0, 0), (x0 + panel - 1, height - 1), frame, 1)

    has_matches = correspondences is not None and len(correspondences) > 0
    if not has_matches or opacity <= 0 or not (show_lines or show_points):
        return base

    raw = np.asarray(correspondences, dtype=float)
    if max_matches is not None:
        raw = raw[: max(0, max_matches)]
    if len(raw) == 0:
        return base

    # Map each side's points through the same portrait rotation (clockwise: (x, y) -> (h-1-y, x))
    # and scale that its image received.
    qx, qy = raw[:, 0].copy(), raw[:, 1].copy()
    if left_rotated:
        qx, qy = left_pre_height - 1 - qy, qx
    tx, ty = raw[:, 2].copy(), raw[:, 3].copy()
    if right_rotated:
        tx, ty = right_pre_height - 1 - ty, tx
    points = np.rint(
        np.stack(
            [
                qx * left_scale + left_pad,
                qy * left_scale,
                tx * right_scale + right_pad,
                ty * right_scale,
            ],
            axis=1,
        )
    ).astype(int)
    count = len(points)

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


class MatchOverlayViewer(QWidget):
    """Result panel + overlay controls + composite viewer for one pairwise comparison."""

    def __init__(self) -> None:
        super().__init__()
        self._comparison: PairwiseComparison | None = None
        self._composite_shape: tuple[int, ...] | None = None
        self._pair: tuple[SourceImage, SourceImage] | None = None
        self._window: QWidget | None = None  # kept alive; a local would be garbage-collected

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self._build_result_panel())
        layout.addWidget(self._build_overlay_controls())
        self.viewer = ImageViewer()
        self.viewer.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.viewer.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.viewer, 1)
        layout.addWidget(self._build_caption_row())

    def _build_caption_row(self) -> QWidget:
        """Two chips naming the panels above them, matching the Mode switch's cells."""
        self._caption_row = QWidget()
        row = QHBoxLayout(self._caption_row)
        row.setContentsMargins(0, 0, 0, 2)
        row.setSpacing(_GAP)  # the same gap the composite leaves between its panels
        self.left_caption = QLabel()
        self.right_caption = QLabel()
        for caption in (self.left_caption, self.right_caption):
            caption.setObjectName("matchCaption")
            caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # Each chip hugs its own text and is centred in an equal half, so it sits under the
            # middle of its panel and reads like the Mode switch's cells rather than a wide bar.
            half = QWidget()
            half_layout = QHBoxLayout(half)
            half_layout.setContentsMargins(0, 0, 0, 0)
            half_layout.addStretch(1)
            half_layout.addWidget(caption)
            half_layout.addStretch(1)
            row.addWidget(half, 1)
        self._caption_row.setVisible(False)
        return self._caption_row

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

        self.detail_label = QLabel("")
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

    # -- public API ------------------------------------------------------------------------
    def set_pair(self, left: SourceImage | None, right: SourceImage | None) -> None:
        """Name the two sides and remember the photographs they came from.

        The names go in the chips under their panels; the photographs back the right-click
        "Show full image". Call before :meth:`show_comparison`; ``None`` drops both.
        """
        self._pair = (left, right) if left is not None and right is not None else None
        self.left_caption.setText(left.title if left is not None else "")
        self.right_caption.setText(right.title if right is not None else "")
        self._caption_row.setVisible(self._pair is not None)
        if self._comparison is not None:
            self._render_composite()

    def pair(self) -> tuple[SourceImage, SourceImage] | None:
        return self._pair

    def show_full_image(self, side: int) -> QWidget | None:
        """Open the whole photograph behind side 0 (left) or 1 (right) of the composite."""
        from herpetoid.gui.widgets.full_image import FullImageWindow

        if self._pair is None:
            return None
        source = self._pair[side]
        if source.image is None:
            return None
        window = FullImageWindow(source.image, roi=source.roi, title=source.title, parent=self)
        self._window = window
        window.show()
        return window

    def _show_context_menu(self, position: QPoint) -> None:
        if self._pair is None:
            return
        menu = QMenu(self)
        for side, source in enumerate(self._pair):
            if source.image is None:
                continue
            action = QAction(f"Show full image — {source.title}", menu)
            action.triggered.connect(lambda _checked=False, s=side: self.show_full_image(s))
            menu.addAction(action)
        if menu.actions():
            menu.exec(self.viewer.mapToGlobal(position))

    def show_comparison(self, comparison: PairwiseComparison) -> None:
        self._comparison = comparison
        self._composite_shape = None
        self._update_result_panel(comparison)
        total = self.match_count(comparison)
        self._set_overlay_controls_enabled(total > 0)
        self.count_spin.blockSignals(True)
        self.count_spin.setRange(0, total)
        self.count_spin.setValue(total)  # show all matches by default
        self.count_spin.blockSignals(False)
        self._render_composite()

    def clear(self) -> None:
        self._comparison = None
        self._composite_shape = None
        self._pair = None
        self._caption_row.setVisible(False)
        self.viewer.clear()
        self.score_label.setText("—")
        self.score_label.setStyleSheet("font-size: 34px; font-weight: 800;")
        self.verdict_label.setText("")
        self.detail_label.setText("")
        self._set_overlay_controls_enabled(False)

    def set_status(self, text: str) -> None:
        self.detail_label.setText(text)

    def comparison(self) -> PairwiseComparison | None:
        return self._comparison

    @staticmethod
    def match_count(comparison: PairwiseComparison) -> int:
        corr = comparison.result.correspondences
        return 0 if corr is None else len(corr)

    # -- rendering ---------------------------------------------------------------------------------
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
            background=self._palette_rgb(QPalette.ColorRole.Base),
            frame=self._palette_rgb(QPalette.ColorRole.Mid),
        )
        # Preserve the user's zoom/rotation across overlay tweaks (the composite size is unchanged).
        keep = self.viewer.has_image() and self._composite_shape == composite.shape
        transform = self.viewer.transform() if keep else None
        self.viewer.set_image(composite)
        if transform is not None:
            self.viewer.setTransform(transform)
        self._composite_shape = composite.shape

    def _update_result_panel(self, comparison: PairwiseComparison) -> None:
        result = comparison.result
        score = float(result.normalized_score)
        if score >= 0.5:
            color, verdict = "#2fae6b", "Strong candidate — compare the patterns to confirm"
        elif score >= 0.25:
            color, verdict = "#e0a13a", "Possible match — look closely"
        else:
            color, verdict = "#d9534f", "Weak — probably a different individual"
        self.score_label.setText(f"{score * 100:.0f}%")
        self.score_label.setStyleSheet(f"font-size: 34px; font-weight: 800; color: {color};")
        self.verdict_label.setText(verdict)
        self.verdict_label.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {color};")
        good = int(result.meta.get("good_matches", 0))
        self.detail_label.setText(
            f"{result.inliers} inlier matches\nof {good} good matches"
        )

    def _palette_rgb(self, role: QPalette.ColorRole) -> tuple[int, int, int]:
        """A palette colour as RGB, so the composite is painted in the interface's own colours."""
        color = self.viewer.palette().color(role)
        return (color.red(), color.green(), color.blue())

    def changeEvent(self, event: QEvent) -> None:
        """Repaint the composite when the theme changes: its background is a palette colour."""
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and self._comparison is not None:
            self._composite_shape = None  # force a refit rather than keeping a stale transform
            self._render_composite()

    def _set_overlay_controls_enabled(self, enabled: bool) -> None:
        for widget in self._overlay_controls:
            widget.setEnabled(enabled)
