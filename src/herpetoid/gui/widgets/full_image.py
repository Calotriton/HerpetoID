"""A pop-out window showing the whole photograph a crop or a comparison was taken from.

The identification views necessarily show *fragments*: a ROI crop, or two normalized patterns laid
side by side. Judging whether two animals are the same one often needs the frame those fragments came
out of — the pose, which flank is showing, how much of the animal is in shot. This window is that
frame, with the marked region outlined so the fragment can be placed inside it, in a pan/zoom viewer
that does not disturb the screen underneath.
"""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QDialog, QVBoxLayout, QWidget

from herpetoid.api import ROI, ROIKind
from herpetoid.gui.widgets.image_viewer import ImageViewer

#: The teal accent, as RGB — the same colour the ROI tools draw with.
_OUTLINE = (47, 158, 143)


def with_roi_outline(image: np.ndarray, roi: ROI | None) -> np.ndarray:
    """A copy of ``image`` with ``roi`` outlined, so a crop can be located within the whole frame."""
    import cv2

    canvas = np.ascontiguousarray(image)
    if canvas.ndim == 2:
        canvas = np.stack([canvas] * 3, axis=-1)
    elif canvas.shape[2] == 4:
        canvas = canvas[:, :, :3]
    canvas = canvas.copy()
    if roi is None:
        return canvas
    height, width = canvas.shape[:2]
    thickness = max(2, round(min(height, width) * 0.005))
    if roi.kind is ROIKind.POLYGON and roi.points:
        points = np.array([[int(x), int(y)] for x, y in roi.points], np.int32)
        cv2.polylines(canvas, [points.reshape(-1, 1, 2)], True, _OUTLINE, thickness, cv2.LINE_AA)
    else:
        box = roi.bounding_box()
        if box is not None:
            x, y, w, h = box
            cv2.rectangle(canvas, (int(x), int(y)), (int(x + w), int(y + h)), _OUTLINE, thickness)
    return canvas


class FullImageWindow(QDialog):
    """A non-modal window showing one photograph, zoomable and pannable.

    Non-modal on purpose: the point is to look at the full frame *while* deciding on the screen
    behind it, and a modal window would also block headless drivers.
    """

    def __init__(
        self,
        image: np.ndarray,
        *,
        roi: ROI | None = None,
        title: str = "Full image",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        self.viewer = ImageViewer()
        layout.addWidget(self.viewer)
        self.viewer.set_image(with_roi_outline(image, roi))
        self.resize(900, 700)
