"""An ImageViewer that also lets the user mark an ROI to isolate the pattern region.

The tool adapts to what a species *declares* in its :class:`~herpetoid.api.ROISpec`:

* ``RECTANGLE`` — click-drag a box (legacy behaviour).
* ``POLYGON`` — click to drop successive vertices around the region, double-click (or *Finish*)
  to close it. Right-click or *Undo* removes the last vertex.

Coordinates are always in image pixels (the scene is 1:1 with the pixmap), so the marked ROI maps
directly to what the species module's preprocessing crops and masks — independent of how the user has
zoomed, panned or rotated the *view*. The view can be rotated freely without affecting the stored ROI.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPen, QPolygonF, QResizeEvent
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsView,
    QHBoxLayout,
    QToolButton,
    QWidget,
)

from herpetoid.api import ROI, ROIKind

from .image_viewer import ImageViewer
from .roi_preview import roi_crop

_ROI_COLOR = QColor(64, 200, 64)
_FILL_COLOR = QColor(64, 200, 64, 45)


class RoiImageViewer(ImageViewer):
    """A pan/zoom/rotate image view with a rectangle- or polygon-drawing ROI tool."""

    roi_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._image: np.ndarray | None = None
        self._draw_mode = False
        self._roi_kind = ROIKind.RECTANGLE  # the kind the tool draws interactively
        self._kind = ROIKind.RECTANGLE  # the kind of the currently held ROI
        self._points: list[QPointF] = []  # rectangle: 2 corners; polygon: N vertices
        self._start: QPointF | None = None  # rectangle drag anchor
        self._building = False  # a polygon is being placed vertex by vertex
        self._cursor: QPointF | None = None  # live cursor while building a polygon
        self._items: list[QGraphicsItem] = []
        self._overlay = self._build_overlay_controls()
        self._overlay.hide()

    def _build_overlay_controls(self) -> QWidget:
        """A small floating toolbar (rotate / reset view) pinned to the image's top-right corner."""
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
        for text, tip, handler in (
            ("⟲", "Rotate left (90° counter-clockwise)", lambda: self.rotate_view(-90)),
            ("⟳", "Rotate right (90° clockwise)", lambda: self.rotate_view(90)),
            ("⤢", "Reset view (fit and clear rotation)", self.reset_view),
        ):
            button = QToolButton(overlay)
            button.setText(text)
            button.setToolTip(tip)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(handler)
            row.addWidget(button)
        overlay.adjustSize()
        return overlay

    def _reposition_overlay(self) -> None:
        self._overlay.adjustSize()
        margin = 8
        self._overlay.move(self.viewport().width() - self._overlay.width() - margin, margin)

    # -- configuration ---------------------------------------------------------------------------
    def set_roi_kind(self, kind: ROIKind) -> None:
        """Choose the geometry the tool draws (from the species' ROISpec). Falls back to rectangle."""
        self._roi_kind = kind if kind in (ROIKind.POLYGON, ROIKind.RECTANGLE) else ROIKind.RECTANGLE
        if not self._points:
            self._kind = self._roi_kind

    def set_draw_mode(self, enabled: bool) -> None:
        self._draw_mode = enabled
        if not enabled and self._building:
            self.finish_polygon()
        self.setDragMode(
            QGraphicsView.DragMode.NoDrag if enabled else QGraphicsView.DragMode.ScrollHandDrag
        )

    # -- image -----------------------------------------------------------------------------------
    def set_image(self, image: np.ndarray) -> None:
        self._image = np.asarray(image)
        self._reset_state()
        super().set_image(image)  # clears the scene (removing our ROI items)
        self._items = []
        self._overlay.show()
        self._overlay.raise_()
        self._reposition_overlay()
        self.roi_changed.emit()

    def clear(self) -> None:
        self._image = None
        self._reset_state()
        super().clear()
        self._items = []
        self._overlay.hide()
        self.roi_changed.emit()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._reposition_overlay()

    # -- view transforms (move / turn) -----------------------------------------------------------
    def rotate_view(self, degrees: float) -> None:
        """Rotate the displayed image about the view centre (does not change stored ROI coords)."""
        if not self.has_image():
            return
        self._auto_fit = False  # rotation is a manual view choice, like zoom
        anchor = self.transformationAnchor()
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.rotate(degrees)
        self.setTransformationAnchor(anchor)

    def reset_view(self) -> None:
        self.resetTransform()  # also clears any rotation
        super().reset_view()

    # -- ROI query / set -------------------------------------------------------------------------
    def roi(self) -> ROI | None:
        if self._kind is ROIKind.POLYGON:
            if len(self._points) < 3:
                return None
            return ROI(
                kind=ROIKind.POLYGON,
                points=tuple((p.x(), p.y()) for p in self._points),
            )
        rect = self._rect()
        if rect is None or rect.width() < 2 or rect.height() < 2:
            return None
        return ROI(
            kind=ROIKind.RECTANGLE,
            points=((rect.left(), rect.top()), (rect.right(), rect.bottom())),
        )

    def set_roi(self, roi: ROI | None) -> None:
        self._reset_state()
        if roi is not None:
            if roi.kind is ROIKind.POLYGON and roi.points:
                self._kind = ROIKind.POLYGON
                self._points = [QPointF(x, y) for x, y in roi.points]
            else:
                box = roi.bounding_box()
                if box is not None:
                    x, y, w, h = box
                    self._kind = ROIKind.RECTANGLE
                    self._points = [QPointF(x, y), QPointF(x + w, y + h)]
        self._redraw()
        self.roi_changed.emit()

    def clear_roi(self) -> None:
        self._reset_state()
        self._redraw()
        self.roi_changed.emit()

    def finish_polygon(self) -> None:
        """Close the polygon currently being placed."""
        if self._building:
            self._building = False
            self._cursor = None
            self._redraw()
            self.roi_changed.emit()

    def undo_point(self) -> None:
        """Remove the most recently placed polygon vertex."""
        if self._kind is ROIKind.POLYGON and self._points:
            self._points.pop()
            if not self._points:
                self._building = False
            self._redraw()
            self.roi_changed.emit()

    def roi_preview(self) -> np.ndarray | None:
        """The cropped (and, for polygons, masked) ROI region, as an RGB uint8 array — or ``None``."""
        return roi_crop(self._image, self.roi())

    # -- interaction -----------------------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if self._draw_mode and self.has_image():
            if event.button() == Qt.MouseButton.LeftButton:
                pos = self.mapToScene(event.position().toPoint())
                if self._roi_kind is ROIKind.POLYGON:
                    self._add_polygon_point(pos)
                else:
                    self._kind = ROIKind.RECTANGLE
                    self._start = pos
                    self._points = [pos, pos]
                    self._redraw()
                return
            if event.button() == Qt.MouseButton.RightButton and self._roi_kind is ROIKind.POLYGON:
                self.undo_point()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._draw_mode and self.has_image():
            if self._roi_kind is ROIKind.RECTANGLE and self._start is not None:
                self._points = [self._start, self.mapToScene(event.position().toPoint())]
                self._redraw()
                return
            if self._roi_kind is ROIKind.POLYGON and self._building:
                self._cursor = self.mapToScene(event.position().toPoint())
                self._redraw()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if (
            self._draw_mode
            and self._roi_kind is ROIKind.RECTANGLE
            and self._start is not None
        ):
            self._points = [self._start, self.mapToScene(event.position().toPoint())]
            self._start = None
            self._redraw()
            self.roi_changed.emit()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if self._draw_mode and self._roi_kind is ROIKind.POLYGON and self._building:
            self.finish_polygon()
            return
        super().mouseDoubleClickEvent(event)

    # -- internals -------------------------------------------------------------------------------
    def _add_polygon_point(self, pos: QPointF) -> None:
        if not self._building:
            self._building = True
            self._kind = ROIKind.POLYGON
            self._points = []
        self._points.append(pos)
        self._redraw()
        self.roi_changed.emit()

    def _reset_state(self) -> None:
        self._points = []
        self._start = None
        self._building = False
        self._cursor = None
        self._kind = self._roi_kind

    def _rect(self) -> QRectF | None:
        if len(self._points) < 2:
            return None
        return QRectF(self._points[0], self._points[1]).normalized()

    def _view_scale(self) -> float:
        transform = self.transform()
        return float(np.hypot(transform.m11(), transform.m12())) or 1.0

    def _pen(self, width: float = 2.0, style: Qt.PenStyle = Qt.PenStyle.SolidLine) -> QPen:
        pen = QPen(_ROI_COLOR)
        pen.setWidthF(width)
        pen.setCosmetic(True)  # constant on-screen width regardless of zoom/rotation
        pen.setStyle(style)
        return pen

    def _redraw(self) -> None:
        for item in self._items:
            self.scene().removeItem(item)
        self._items = []
        if not self.has_image():
            return
        if self._kind is ROIKind.POLYGON:
            self._draw_polygon()
        else:
            rect = self._rect()
            if rect is not None:
                self._items.append(self.scene().addRect(rect, self._pen()))

    def _draw_polygon(self) -> None:
        if not self._points:
            return
        scene = self.scene()
        closed = not self._building and len(self._points) >= 3
        if closed:
            polygon = QPolygonF(self._points)
            self._items.append(scene.addPolygon(polygon, self._pen(), QBrush(_FILL_COLOR)))
        else:
            for a, b in zip(self._points, self._points[1:], strict=False):
                self._items.append(scene.addLine(a.x(), a.y(), b.x(), b.y(), self._pen()))
            if self._cursor is not None:
                last = self._points[-1]
                self._items.append(
                    scene.addLine(
                        last.x(), last.y(), self._cursor.x(), self._cursor.y(), self._pen()
                    )
                )
                if len(self._points) >= 2:
                    first = self._points[0]
                    self._items.append(
                        scene.addLine(
                            self._cursor.x(),
                            self._cursor.y(),
                            first.x(),
                            first.y(),
                            self._pen(1.0, Qt.PenStyle.DashLine),
                        )
                    )
        radius = 3.0 / self._view_scale()
        vertex_pen = self._pen(1.0)
        vertex_brush = QBrush(_ROI_COLOR)
        for point in self._points:
            self._items.append(
                scene.addEllipse(
                    point.x() - radius,
                    point.y() - radius,
                    radius * 2,
                    radius * 2,
                    vertex_pen,
                    vertex_brush,
                )
            )
