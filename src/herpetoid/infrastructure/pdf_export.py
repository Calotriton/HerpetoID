"""PDF export: a project report and per-individual dossiers (ReportLab).

Complementary, on-demand export (not part of the base data exporters). Embeds observation thumbnails
from the bundle when a bundle root is provided.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from PIL import Image as PilImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image as RLImage,
)
from reportlab.platypus import (
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    TableStyle,
)

from herpetoid.application.export import ExportData
from herpetoid.domain import Image, Individual, Observation

_TABLE_STYLE = TableStyle(
    [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2679c8")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f6fb")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
)


def _table(rows: list[list[str]]) -> LongTable:
    table = LongTable(rows, repeatRows=1)
    table.setStyle(_TABLE_STYLE)
    return table


def _date(observation: Observation) -> str:
    return observation.observed_at.isoformat()[:10] if observation.observed_at is not None else ""


class PdfExporter:
    format_id = "pdf"

    def __init__(
        self, bundle_root: Path | None = None, *, title: str = "HerpetoID Report", author: str = ""
    ) -> None:
        self._bundle_root = bundle_root
        self._title = title
        self._author = author

    def export(self, data: ExportData, destination: Path) -> None:
        styles = getSampleStyleSheet()
        story: list[Any] = [
            Paragraph(self._title, styles["Title"]),
            Paragraph(f"Project: {data.project.name}", styles["Heading2"]),
        ]
        if data.project.description:
            story.append(Paragraph(data.project.description, styles["Normal"]))
        story.append(Spacer(1, 5 * mm))
        story.append(
            Paragraph(
                f"Individuals: {len(data.individuals)} &nbsp;&nbsp; "
                f"Observations: {len(data.observations)}",
                styles["Normal"],
            )
        )
        story.append(Spacer(1, 6 * mm))

        counts = self._observation_counts(data.observations)
        story.append(Paragraph("Individuals", styles["Heading2"]))
        individual_rows = [["Code", "Sex", "Status", "Observations"]]
        for individual in data.individuals:
            individual_rows.append(
                [
                    individual.code,
                    str(individual.sex),
                    str(individual.status),
                    str(counts.get(individual.id, 0)),
                ]
            )
        story.append(_table(individual_rows))
        story.append(Spacer(1, 6 * mm))

        species_names = {s.id: s.scientific_name for s in data.species}
        story.append(Paragraph("Observations", styles["Heading2"]))
        observation_rows = [["ID", "Species", "Observer", "Date"]]
        for observation in data.observations:
            observation_rows.append(
                [
                    str(observation.id),
                    species_names.get(observation.species_id, ""),
                    observation.observer,
                    _date(observation),
                ]
            )
        story.append(_table(observation_rows))

        images_by_observation = self._images_by_observation(data.images)
        for individual in data.individuals:
            story.extend(self._dossier(individual, data, styles, images_by_observation))

        document = SimpleDocTemplate(
            str(destination),
            pagesize=A4,
            title=self._title,
            author=self._author,
            topMargin=18 * mm,
            bottomMargin=18 * mm,
        )
        document.build(story)

    def _dossier(
        self,
        individual: Individual,
        data: ExportData,
        styles: Any,
        images_by_observation: dict[int, list[Image]],
    ) -> list[Any]:
        observations = [o for o in data.observations if o.individual_id == individual.id]
        elements: list[Any] = [
            Spacer(1, 8 * mm),
            Paragraph(f"Individual {individual.code}", styles["Heading2"]),
            Paragraph(f"Sex: {individual.sex} · Status: {individual.status}", styles["Normal"]),
        ]
        thumbnail = self._first_thumbnail(observations, images_by_observation)
        if thumbnail is not None:
            elements.append(Spacer(1, 3 * mm))
            elements.append(thumbnail)
        rows = [["Obs", "Observer", "Date", "Measurements"]]
        for observation in observations:
            measurements = ", ".join(f"{k}={v}" for k, v in observation.measurements.items())
            rows.append(
                [str(observation.id), observation.observer, _date(observation), measurements]
            )
        elements.append(Spacer(1, 3 * mm))
        elements.append(_table(rows))
        return elements

    def _first_thumbnail(
        self, observations: list[Observation], images_by_observation: dict[int, list[Image]]
    ) -> RLImage | None:
        if self._bundle_root is None:
            return None
        for observation in observations:
            if observation.id is None:
                continue
            for image in images_by_observation.get(observation.id, []):
                if not image.thumbnail_path:
                    continue
                path = self._bundle_root / image.thumbnail_path
                if path.exists():
                    return self._rl_image(path)
        return None

    @staticmethod
    def _rl_image(path: Path) -> RLImage:
        with PilImage.open(path) as opened:
            width_px, height_px = opened.size
        width = 45 * mm
        height = width * (height_px / width_px) if width_px else width
        return RLImage(str(path), width=width, height=height)

    @staticmethod
    def _observation_counts(observations: Any) -> dict[int | None, int]:
        counts: dict[int | None, int] = {}
        for observation in observations:
            if observation.individual_id is not None:
                counts[observation.individual_id] = counts.get(observation.individual_id, 0) + 1
        return counts

    @staticmethod
    def _images_by_observation(images: Any) -> dict[int, list[Image]]:
        grouped: dict[int, list[Image]] = {}
        for image in images:
            grouped.setdefault(image.observation_id, []).append(image)
        return grouped
