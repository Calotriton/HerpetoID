"""Species module for *Calotriton asper* (Pyrenean brook newt).

Identification uses the individual's unique **ventral** (belly) spot pattern. The user marks the ventral
region (a polygon ROI); preprocessing normalizes it into a grayscale, contrast-enhanced
:class:`~herpetoid.api.Sample` suitable for keypoint algorithms (ORB).
"""

from __future__ import annotations

from typing import Any

import cv2
import numpy as np

from herpetoid.api import (
    ROI,
    AlgorithmCompatibility,
    AlgorithmFamily,
    DerivedStatistic,
    ExportFormatSpec,
    FieldDefinition,
    FieldGroup,
    FieldType,
    ModuleContext,
    ModuleDescriptor,
    ROIKind,
    ROISpec,
    Sample,
    SpeciesModule,
    SpeciesProfile,
    StatisticKind,
    Validation,
)

_DEFAULT_CONFIG: dict[str, Any] = {
    "denoise": True,
    "denoise_strength": 10.0,
    "use_clahe": False,  # global histogram equalization by default; CLAHE optional
    "clahe_clip": 2.0,
    "clahe_grid": 8,
}


def _scale_to_u8(array: np.ndarray) -> np.ndarray:
    values = array.astype(np.float64)
    low, high = float(values.min()), float(values.max())
    if high <= low:
        return np.zeros(values.shape, dtype=np.uint8)
    return ((values - low) / (high - low) * 255.0).astype(np.uint8)


class CalotritonAsperModule(SpeciesModule):
    """Ventral-pattern species module for *Calotriton asper*."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config: dict[str, Any] = {**_DEFAULT_CONFIG, **(config or {})}

    @classmethod
    def descriptor(cls) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="calotriton_asper",
            name="Calotriton asper (Pyrenean brook newt)",
            version="1.0",
            supported_species=("Calotriton asper",),
            description="Ventral-pattern identification for the Pyrenean brook newt.",
        )

    def initialize(self, ctx: ModuleContext) -> None:
        self._config = {**self._config, **dict(ctx.config)}

    def define_species_profile(self) -> SpeciesProfile:
        measurements = (
            FieldDefinition(
                "svl",
                "SVL",
                FieldType.FLOAT,
                group=FieldGroup.MEASUREMENT,
                unit="mm",
                validation=Validation(min_value=0.0),
                include_in_statistics=True,
                order=1,
            ),
            FieldDefinition(
                "weight",
                "Weight",
                FieldType.FLOAT,
                group=FieldGroup.MEASUREMENT,
                unit="g",
                validation=Validation(min_value=0.0),
                include_in_statistics=True,
                order=2,
            ),
            FieldDefinition(
                "sex",
                "Sex",
                FieldType.CHOICE,
                group=FieldGroup.GENERAL,
                choices=("male", "female", "undetermined"),
                include_in_statistics=True,
                order=3,
            ),
            FieldDefinition(
                "life_stage",
                "Life stage",
                FieldType.CHOICE,
                group=FieldGroup.GENERAL,
                choices=("larva", "juvenile", "subadult", "adult"),
                include_in_statistics=True,
                order=4,
            ),
        )
        derived_statistics = (
            DerivedStatistic(
                "mean_svl", "Mean SVL", StatisticKind.AGGREGATE, source_field="svl", unit="mm"
            ),
            DerivedStatistic(
                "mean_weight",
                "Mean weight",
                StatisticKind.AGGREGATE,
                source_field="weight",
                unit="g",
            ),
            DerivedStatistic(
                "sex_ratio", "Sex ratio", StatisticKind.DISTRIBUTION, source_field="sex"
            ),
            DerivedStatistic(
                "svl_growth",
                "Growth (SVL over time)",
                StatisticKind.GROWTH,
                source_field="svl",
                unit="mm",
            ),
        )
        return SpeciesProfile(
            scientific_name="Calotriton asper",
            common_name="Pyrenean brook newt",
            taxonomy={
                "class": "Amphibia",
                "order": "Urodela",
                "family": "Salamandridae",
                "genus": "Calotriton",
            },
            description="A stream-dwelling newt endemic to the Pyrenees and nearby ranges.",
            identification_notes=(
                "Individuals carry a unique ventral (belly) pattern of dark spots on a paler ground, "
                "stable over time and used for photo-identification."
            ),
            pattern_region="ventral",
            roi=ROISpec(
                kind=ROIKind.POLYGON,
                interactive=True,
                guidance="Draw a polygon around the ventral (belly) pattern.",
            ),
            compatible_algorithms=AlgorithmCompatibility(
                families=(AlgorithmFamily.KEYPOINT,), requires_grayscale=True
            ),
            measurements=measurements,
            derived_statistics=derived_statistics,
            export_formats=(
                ExportFormatSpec("csv"),
                ExportFormatSpec("xlsx"),
                ExportFormatSpec("json"),
                ExportFormatSpec("pdf"),
            ),
        )

    def preprocess(self, image: np.ndarray, roi: ROI) -> Sample:
        config = self._config
        full_mask = self._roi_mask(image, roi)
        box = roi.bounding_box()
        if box is not None:
            x, y, w, h = box
            x0, y0 = max(0, x), max(0, y)
            x1, y1 = min(image.shape[1], x + w), min(image.shape[0], y + h)
            region = image[y0:y1, x0:x1]
            region_mask = full_mask[y0:y1, x0:x1] if full_mask is not None else None
        else:
            region = image
            region_mask = full_mask

        if region.ndim == 2:
            gray = np.asarray(region)
        else:
            gray = np.asarray(cv2.cvtColor(region, cv2.COLOR_RGB2GRAY))
        if gray.dtype != np.uint8:
            gray = _scale_to_u8(gray)
        if config["denoise"]:
            gray = cv2.fastNlMeansDenoising(gray, None, float(config["denoise_strength"]))
        if config["use_clahe"]:
            clahe = cv2.createCLAHE(
                clipLimit=float(config["clahe_clip"]),
                tileGridSize=(int(config["clahe_grid"]), int(config["clahe_grid"])),
            )
            gray = clahe.apply(gray)
        else:
            gray = cv2.equalizeHist(gray)

        return Sample(
            image=np.ascontiguousarray(gray),
            roi_mask=region_mask,
            color_space="gray",
            meta={"species": "Calotriton asper"},
        )

    @staticmethod
    def _roi_mask(image: np.ndarray, roi: ROI) -> np.ndarray | None:
        if roi.kind is ROIKind.POLYGON and roi.points:
            mask = np.zeros(image.shape[:2], dtype=np.uint8)
            points = np.array(roi.points, dtype=np.int32).reshape(-1, 1, 2)
            cv2.fillPoly(mask, [points], 255)
            return mask
        if roi.mask is not None:
            return (np.asarray(roi.mask) > 0).astype(np.uint8) * 255
        return None
