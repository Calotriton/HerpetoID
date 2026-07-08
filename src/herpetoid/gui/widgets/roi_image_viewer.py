"""An ImageViewer that also lets the user draw a rectangular ROI to isolate the pattern region.

Coordinates are in image pixels (the scene is 1:1 with the pixmap), so the ROI maps directly to what
the species module's preprocessing crops.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QMouseEvent, QPen
from PySide6.QtWidgets import QGraphicsRectItem, QGraphicsView, QWidget

from herpetoid.api import ROI, ROIKind

from .image_viewer import ImageViewer


class RoiImageViewer(ImageViewer):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._draw_mode = False
        self._roi_item: QGraphicsRectItem | None = None
        self._start: QPointF | None = None
        self._roi_rect: QRectF | None = None

    def set_draw_mode(self, enabled: bool) -> None:
        self._draw_mode = enabled
        self.setDragMode(
            QGraphicsView.DragMode.NoDrag if enabled else QGraphicsView.DragMode.ScrollHandDrag
        )

    def set_image(self, image: np.ndarray) -> None:
        self._roi_item = None  # cleared by the scene reset in the base class
        self._roi_rect = None
        super().set_image(image)

    def clear_roi(self) -> None:
        self._remove_roi_item()
        self._roi_rect = None

    def roi(self) -> ROI | None:
        if self._roi_rect is None or self._roi_rect.width() < 2 or self._roi_rect.height() < 2:
            return None
        rect = self._roi_rect
        return ROI(
            kind=ROIKind.RECTANGLE,
            points=((rect.left(), rect.top()), (rect.right(), rect.bottom())),
        )

    def set_roi(self, roi: ROI | None) -> None:
        self._remove_roi_item()
        self._roi_rect = None
        if roi is None:
            return
        box = roi.bounding_box()
        if box is None:
            return
        x, y, w, h = box
        self._roi_rect = QRectF(x, y, w, h)
        self._draw_roi_item()

    def _draw_roi_item(self) -> None:
        self._remove_roi_item()
        if self._roi_rect is None:
            return
        pen = QPen(QColor(64, 200, 64))
        pen.setWidth(2)
        pen.setCosmetic(True)  # constant on-screen width regardless of zoom
        self._roi_item = self.scene().addRect(self._roi_rect, pen)

    def _remove_roi_item(self) -> None:
        if self._roi_item is not None:
            self.scene().removeItem(self._roi_item)
            self._roi_item = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._draw_mode and event.button() == Qt.MouseButton.LeftButton and self.has_image():
            self._start = self.mapToScene(event.position().toPoint())
            self._roi_rect = QRectF(self._start, self._start)
            self._draw_roi_item()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._draw_mode and self._start is not None:
            self._roi_rect = QRectF(
                self._start, self.mapToScene(event.position().toPoint())
            ).normalized()
            self._draw_roi_item()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._draw_mode and self._start is not None:
            self._roi_rect = QRectF(
                self._start, self.mapToScene(event.position().toPoint())
            ).normalized()
            self._start = None
            self._draw_roi_item()
            return
        super().mouseReleaseEvent(event)
