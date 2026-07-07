"""The declarative Species Profile manifest and its parts.

A :class:`SpeciesProfile` is the single source of truth for a species. Core is a generic engine that
renders it into forms, comparison panels, statistics dashboards and exports — it contains no
species-specific logic.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .enums import Aggregation, AlgorithmFamily, StatisticKind
from .fields import FieldDefinition
from .imaging import ROISpec


@dataclass(frozen=True, slots=True)
class ReferenceImage:
    """A bundled reference/example image for a species profile (loaded via importlib.resources)."""

    resource: str  # path relative to the module's package
    caption: str = ""


@dataclass(frozen=True, slots=True)
class AlgorithmCompatibility:
    """Capability-based declaration of which algorithms a module's :class:`Sample` suits.

    Modules declare *capabilities*, not concrete algorithm ids, so the two plugin kinds stay
    decoupled. Optional allow/deny id lists override capability matching for edge cases.
    """

    families: tuple[AlgorithmFamily, ...] = (AlgorithmFamily.KEYPOINT,)
    requires_grayscale: bool = False
    requires_mask: bool = False
    allow_ids: tuple[str, ...] = ()
    deny_ids: tuple[str, ...] = ()

    def accepts_family(self, family: AlgorithmFamily) -> bool:
        return family in self.families


@dataclass(frozen=True, slots=True)
class DerivedStatistic:
    """A statistic Core computes and displays. Field-driven for the common cases; a pure callable for
    custom derived metrics (e.g. body-condition index = weight / SVL**3).
    """

    key: str
    label: str
    kind: StatisticKind
    source_field: str | None = None  # observation field key (AGGREGATE / DISTRIBUTION / GROWTH)
    aggregation: Aggregation = Aggregation.MEAN
    unit: str | None = None
    #: For DERIVED: maps a mapping of field-key -> value to a number (or None if not computable).
    compute: Callable[[Mapping[str, Any]], float | None] | None = None

    def __post_init__(self) -> None:
        if self.kind is StatisticKind.DERIVED:
            if self.compute is None:
                raise ValueError(f"derived statistic {self.key!r} requires a 'compute' callable")
        elif not self.source_field:
            raise ValueError(f"statistic {self.key!r} of kind {self.kind} requires 'source_field'")


@dataclass(frozen=True, slots=True)
class ExportFormatSpec:
    """Declarative selection/configuration of one Core-registered exporter for this species."""

    exporter_id: str  # e.g. 'csv', 'xlsx', 'json', 'pdf'
    label: str = ""
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SpeciesProfile:
    """The declarative manifest for a species."""

    scientific_name: str
    common_name: str = ""
    taxonomy: Mapping[str, str] = field(default_factory=dict)  # rank -> name
    description: str = ""
    identification_notes: str = ""
    pattern_region: str = ""  # e.g. 'ventral', 'dorsal flank'
    references: tuple[str, ...] = ()
    reference_images: tuple[ReferenceImage, ...] = ()
    roi: ROISpec = field(default_factory=ROISpec)
    compatible_algorithms: AlgorithmCompatibility = field(default_factory=AlgorithmCompatibility)
    measurements: tuple[FieldDefinition, ...] = ()
    derived_statistics: tuple[DerivedStatistic, ...] = ()
    export_formats: tuple[ExportFormatSpec, ...] = ()

    def __post_init__(self) -> None:
        if not self.scientific_name:
            raise ValueError("SpeciesProfile.scientific_name must be non-empty")
