"""Concrete file exporters (CSV, Excel, JSON) implementing the export port."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from openpyxl import Workbook

from herpetoid.application.export import ExportData, Exporter, observation_rows


class CsvExporter:
    format_id = "csv"

    def export(self, data: ExportData, destination: Path) -> None:
        columns, rows = observation_rows(data)
        with destination.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns)
            writer.writeheader()
            writer.writerows(rows)


class JsonExporter:
    format_id = "json"

    def export(self, data: ExportData, destination: Path) -> None:
        _columns, rows = observation_rows(data)
        payload = {
            "project": {
                "name": data.project.name,
                "uuid": data.project.uuid,
                "description": data.project.description,
            },
            "individuals": [
                {
                    "id": individual.id,
                    "code": individual.code,
                    "name": individual.name,
                    "sex": str(individual.sex),
                    "status": str(individual.status),
                    "notes": individual.notes,
                }
                for individual in data.individuals
            ],
            "observations": rows,
        }
        destination.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


class ExcelExporter:
    format_id = "xlsx"

    def export(self, data: ExportData, destination: Path) -> None:
        columns, rows = observation_rows(data)
        workbook = Workbook()
        observations_sheet = workbook.active
        observations_sheet.title = "Observations"
        observations_sheet.append(columns)
        for row in rows:
            observations_sheet.append([row.get(column) for column in columns])

        individuals_sheet = workbook.create_sheet("Individuals")
        individuals_sheet.append(["id", "code", "name", "sex", "status", "notes"])
        for individual in data.individuals:
            individuals_sheet.append(
                [
                    individual.id,
                    individual.code,
                    individual.name,
                    str(individual.sex),
                    str(individual.status),
                    individual.notes,
                ]
            )
        workbook.save(destination)


def default_exporters() -> list[Exporter]:
    """The exporters shipped in the base app (CSV, Excel, JSON)."""
    return [CsvExporter(), ExcelExporter(), JsonExporter()]
