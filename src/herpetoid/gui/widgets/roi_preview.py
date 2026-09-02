"""A small read-only preview of an image's marked ROI region (cropped, polygon-masked).

Reused next to the info tables in Candidates and Individuals so the selected pattern region can be
compared visually alongside the numeric data.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtWidgets import QFrame, QLabel, QMenu, QWidget

from herpetoid.api import ROI, ROIKind

from .image_viewer import ndarray_to_qimage


def _to_rgb_u8(region: np.ndarray) -> np.ndarray:
    array = np.asarray(region)
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


def roi_crop(image: np.ndarray | None, roi: ROI | None) -> np.ndarray | None:
    """The ROI region of ``image`` as an RGB uint8 array (polygons masked, outside dimmed)."""
    if image is None or roi is None:
        return None
    box = roi.bounding_box()
    if box is None:
        return None
    x, y, w, h = box
    height, width = image.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(width, x + w), min(height, y + h)
    if x1 <= x0 or y1 <= y0:
        return None
    rgb = _to_rgb_u8(image[y0:y1, x0:x1])
    if roi.kind is ROIKind.POLYGON and roi.points:
        import cv2

        mask = np.zeros((y1 - y0, x1 - x0), np.uint8)
        pts = np.array([[px - x0, py - y0] for px, py in roi.points], np.int32)
        cv2.fillPoly(mask, [pts.reshape(-1, 1, 2)], 255)
        dimmed = (rgb.astype(np.float32) * 0.25).astype(np.uint8)
        rgb = np.where(mask[:, :, None] > 0, rgb, dimmed).astype(np.uint8)
    return np.ascontiguousarray(rgb)


class RoiPreview(QLabel):
    """A fixed-size panel that renders an image's ROI crop, or a placeholder when there is none.

    Right-clicking offers the whole photograph the crop came out of (see
    :class:`~herpetoid.gui.widgets.full_image.FullImageWindow`): a masked crop shows the pattern but
    not the pose or the framing, which is often what settles a doubtful match.
    """

    def __init__(
        self, width: int = 150, height: int = 120, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._image: np.ndarray | None = None
        self._roi: ROI | None = None
        self._title = "Full image"
        self._window: QWidget | None = None  # kept alive; a local would be garbage-collected
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.clear_preview()

    def show_roi(self, image: np.ndarray | None, roi: ROI | None, *, title: str = "") -> None:
        """Render ``roi`` of ``image``. ``title`` names the pop-out window for this photograph."""
        self._image = image
        self._roi = roi
        self._title = title or "Full image"
        crop = roi_crop(image, roi)
        if crop is None:
            self.setPixmap(QPixmap())
            self.setText("No ROI")
            self._update_tooltip()
            return
        pixmap = QPixmap.fromImage(ndarray_to_qimage(crop)).scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(pixmap)
        self._update_tooltip()

    def clear_preview(self) -> None:
        self._image = None
        self._roi = None
        self.setPixmap(QPixmap())
        self.setText("No ROI")
        self._update_tooltip()

    def has_full_image(self) -> bool:
        """Whether there is a photograph behind this crop to pop out."""
        return self._image is not None

    def show_full_image(self) -> QWidget | None:
        """Open the whole photograph this crop came from, with the region outlined."""
        from herpetoid.gui.widgets.full_image import FullImageWindow

        if self._image is None:
            return None
        window = FullImageWindow(self._image, roi=self._roi, title=self._title, parent=self)
        self._window = window
        window.show()
        return window

    def _update_tooltip(self) -> None:
        self.setToolTip(
            "Selected ROI region — right-click to see the full photograph"
            if self._image is not None
            else "Selected ROI region"
        )

    def _show_context_menu(self, position: QPoint) -> None:
        if self._image is None:
            return
        menu = QMenu(self)
        action = QAction("Show full image", menu)
        action.triggered.connect(self.show_full_image)
        menu.addAction(action)
        menu.exec(self.mapToGlobal(position))
