"""An interactive image viewer with zoom (wheel) and pan (drag).

Reused across image import, the observation editor (ROI), the comparison window and dossiers. Displays
NumPy image arrays (grayscale or RGB/RGBA) via a ``QGraphicsView``.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap, QWheelEvent
from PySide6.QtWidgets import QGraphicsPixmapItem, QGraphicsScene, QGraphicsView, QWidget

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
    """A pan/zoom image view."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self._pixmap_item: QGraphicsPixmapItem | None = None
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)  # click-drag to pan
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)

    def set_image(self, image: np.ndarray) -> None:
        pixmap = QPixmap.fromImage(ndarray_to_qimage(image))
        self._scene.clear()
        self._pixmap_item = self._scene.addPixmap(pixmap)
        self._scene.setSceneRect(QRectF(pixmap.rect()))
        self.reset_view()

    def clear(self) -> None:
        self._scene.clear()
        self._pixmap_item = None

    def has_image(self) -> bool:
        return self._pixmap_item is not None

    def reset_view(self) -> None:
        if self._pixmap_item is not None:
            self.fitInView(self._pixmap_item, Qt.AspectRatioMode.KeepAspectRatio)

    def current_scale(self) -> float:
        return float(self.transform().m11())

    def zoom(self, factor: float) -> None:
        target = self.current_scale() * factor
        if _MIN_SCALE <= target <= _MAX_SCALE:
            self.scale(factor, factor)

    def wheelEvent(self, event: QWheelEvent) -> None:
        self.zoom(1.25 if event.angleDelta().y() > 0 else 1 / 1.25)
