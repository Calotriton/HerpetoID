"""An interactive image viewer with zoom (wheel) and pan (drag).

Reused across image import, the observation editor (ROI), the comparison window and dossiers. Displays
NumPy image arrays (grayscale or RGB/RGBA) via a ``QGraphicsView``.

The view keeps the image fitted (on show and resize) until the user zooms manually — this avoids the
common ``fitInView`` pitfall where fitting before the widget has its final on-screen size leaves the
image scaled to nothing.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QImage, QPainter, QPixmap, QResizeEvent, QShowEvent, QWheelEvent
from PySide6.QtWidgets import (
    QGraphicsPixmapItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QToolButton,
    QWidget,
)

_MIN_SCALE = 0.05
_MAX_SCALE = 40.0


def ndarray_to_qimage(image: np.ndarray) -> QImage:
    """Convert a grayscale or RGB/RGBA ``uint8`` array to a (detached) ``QImage``."""
    array = np.ascontiguousarray(image)
    if array.ndim == 2:
        height, width = array.shape
        return QImage(array.data, width, height, width, QImage.Format.Format_Grayscale8).copy()
    height, width, channels = array.shape
    if channels == 3:
        return QImage(array.data, width, height, 3 * width, QImage.Format.Format_RGB888).copy()
    if channels == 4:
        return QImage(array.data, width, height, 4 * width, QImage.Format.Format_RGBA8888).copy()
    raise ValueError(f"unsupported image shape {array.shape!r}")


class ImageViewer(QGraphicsView):
    """A pan/zoom image view, optionally with a floating turn/fit toolbar."""

    #: A quarter turn was asked for (clockwise degrees), by the toolbar. The screen owning
    #: the capture decides what that means — it records the turn, so every other view shows
    #: the same orientation rather than it being a transform of this view alone.
    rotation_requested = Signal(int)

    def __init__(self, parent: QWidget | None = None, *, view_tools: bool = False) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self._auto_fit = True
        self._view_tools: QWidget | None = None
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)  # click-drag to pan
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        if view_tools:
            self._view_tools = self._build_view_tools()

    def set_image(self, image: np.ndarray) -> None:
        pixmap = QPixmap.fromImage(ndarray_to_qimage(image))
        self._scene.clear()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self.reset_view()
        if self._view_tools is not None:
            self._view_tools.show()
            self._view_tools.raise_()
            self._reposition_view_tools()

    def clear(self) -> None:
        self._scene.clear()
        self._pixmap_item = None
        if self._view_tools is not None:
            self._view_tools.hide()

    def has_image(self) -> bool:
        return self._pixmap_item is not None

    def image_shape(self) -> tuple[int, int] | None:
        """The displayed image's (height, width), or ``None`` when nothing is shown."""
        if self._pixmap_item is None:
            return None
        size = self._pixmap_item.pixmap().size()
        return size.height(), size.width()

    def reset_view(self) -> None:
        self._auto_fit = True
        self._fit()

    def current_scale(self) -> float:
        # Magnitude of the transform's X basis vector — robust to rotation (m11 alone goes to 0 at 90°).
        transform = self.transform()
        return float((transform.m11() ** 2 + transform.m12() ** 2) ** 0.5) or 1.0

    def zoom(self, factor: float) -> None:
        current = self.current_scale()
        target = max(_MIN_SCALE, min(_MAX_SCALE, current * factor))
        applied = target / current
        if abs(applied - 1.0) < 1e-3:  # already at the min/max limit
            return
        self._auto_fit = False  # the user has taken control of the zoom level
        self.scale(applied, applied)

    def _fit(self) -> None:
        if self._pixmap_item is not None:
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event: QWheelEvent) -> None:
        delta = event.angleDelta().y() or event.pixelDelta().y()
        if delta == 0:
            return
        self.zoom(1.25 if delta > 0 else 1 / 1.25)
        event.accept()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if self._auto_fit:
            self._fit()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._auto_fit:
            self._fit()
        self._reposition_view_tools()

    def _build_view_tools(self) -> QWidget:
        """A small floating toolbar (turn / fit) pinned to the image's top-right corner.

        The buttons only *ask*: what a quarter turn means belongs to the screen that owns the
        capture, which records it so every other view shows the same orientation.
        """
        overlay = QWidget(self.viewport())
        overlay.setObjectName("viewOverlay")
        overlay.setStyleSheet(
            "#viewOverlay { background: rgba(20, 22, 25, 0.72); border-radius: 8px; }"
            " QToolButton { color: white; border: none; padding: 4px 6px; font-size: 14px; }"
            " QToolButton:hover { background: rgba(255, 255, 255, 0.18); border-radius: 5px; }"
        )
        row = QHBoxLayout(overlay)
        row.setContentsMargins(4, 2, 4, 2)
        row.setSpacing(2)
        for label, tip, handler in (
            (
                "\u27f2",
                "Turn left (90\u00b0 counter-clockwise) \u2014 kept with the capture, everywhere",
                lambda: self.rotation_requested.emit(-90),
            ),
            (
                "\u27f3",
                "Turn right (90\u00b0 clockwise) \u2014 kept with the capture, everywhere",
                lambda: self.rotation_requested.emit(90),
            ),
            ("\u2922", "Reset view (fit to the window)", self.reset_view),
        ):
            button = QToolButton(overlay)
            button.setText(label)
            button.setToolTip(tip)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(handler)
            row.addWidget(button)
        overlay.adjustSize()
        overlay.hide()
        return overlay

    def _reposition_view_tools(self) -> None:
        if self._view_tools is None:
            return
        self._view_tools.adjustSize()
        margin = 8
        self._view_tools.move(self.viewport().width() - self._view_tools.width() - margin, margin)

