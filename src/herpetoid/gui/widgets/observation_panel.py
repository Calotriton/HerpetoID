"""A titled observation panel: image viewer + species-driven info table + ROI crop.

Shared by the identification views so query and candidate render identically. The loaders take the
:class:`AppState` per call (the panel holds no state of its own beyond the widgets).
"""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from herpetoid.api import ROI
from herpetoid.gui.state import AppState
from herpetoid.gui.widgets.image_viewer import ImageViewer
from herpetoid.gui.widgets.info_table import (
    InfoTable,
    observation_info_rows,
    species_field_definitions,
)
from herpetoid.gui.widgets.roi_preview import RoiPreview


class ObservationPanel(QWidget):
    """Image (dominant), with the observation's data box and ROI crop beneath."""

    def __init__(self, title: str) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.title_label = QLabel(f"<b>{title}</b>")
        layout.addWidget(self.title_label)
        self.viewer = ImageViewer()
        layout.addWidget(self.viewer, 3)
        data_row = QHBoxLayout()
        self.info = InfoTable()
        data_row.addWidget(self.info, 1)
        roi_box = QVBoxLayout()
        roi_box.addWidget(QLabel("ROI"))
        self.roi = RoiPreview()
        roi_box.addWidget(self.roi)
        roi_box.addStretch(1)
        data_row.addLayout(roi_box)  # the ROI crop sits beside the data box for visual comparison
        layout.addLayout(data_row, 2)

    def clear(self) -> None:
        self.viewer.clear()
        self.info.clear_rows()
        self.roi.clear_preview()

    def show_observation(
        self,
        state: AppState,
        observation_id: int | None,
        *,
        individual_code: str | None = None,
    ) -> None:
        """Load the observation's first image, info rows and ROI crop (clearing on any miss)."""
        self.clear()
        if observation_id is None:
            return
        show_observation_image(state, self.viewer, observation_id)
        show_observation_info(
            state, self.info, self.roi, observation_id, individual_code=individual_code
        )


def show_observation_info(
    state: AppState,
    info_table: InfoTable,
    roi_preview: RoiPreview,
    observation_id: int | None,
    *,
    individual_code: str | None = None,
) -> None:
    info_table.clear_rows()
    roi_preview.clear_preview()
    catalog = state.catalog
    if catalog is None or observation_id is None:
        return
    observation = catalog.get_observation(observation_id)
    if observation is None:
        return
    code = individual_code
    if code is None and observation.individual_id is not None:
        individual = catalog.get_individual(observation.individual_id)
        code = individual.code if individual is not None else None
    fields = species_field_definitions(state, observation.species_id)
    info_table.show_rows(observation_info_rows(observation, fields, individual_code=code))
    image, roi = observation_image_and_roi(state, observation_id)
    # Name the pop-out window after the capture, so several open at once stay tellable apart.
    title = f"{code} · Observation {observation_id}" if code else f"Observation {observation_id}"
    roi_preview.show_roi(image, roi, title=title)


def observation_image_and_roi(
    state: AppState, observation_id: int
) -> tuple[np.ndarray | None, ROI | None]:
    catalog = state.catalog
    project = state.project
    if catalog is None or project is None:
        return None, None
    images = catalog.images_for(observation_id)
    if not images or images[0].id is None:
        return None, None
    try:
        image = project.image_store.load(images[0].rel_path)
    except (OSError, ValueError):
        return None, None
    return image, catalog.get_image_roi(images[0].id)


def show_observation_image(state: AppState, viewer: ImageViewer, observation_id: int) -> None:
    catalog = state.catalog
    if catalog is None:
        return
    images = catalog.images_for(observation_id)
    if images:
        show_image_rel_path(state, viewer, images[0].rel_path)


def show_image_rel_path(state: AppState, viewer: ImageViewer, rel_path: str) -> None:
    project = state.project
    if project is None:
        return
    try:
        viewer.set_image(project.image_store.load(rel_path))
    except (OSError, ValueError):
        viewer.clear()
