"""HerpetoID plugin SDK — the Qt-free contract between Core and its plugins.

Species modules subclass :class:`SpeciesModule`; identification algorithms subclass
:class:`IdentificationAlgorithm`. Everything here is pure Python + NumPy and imports **no** GUI
framework, so plugins stay lightweight and unit-testable.
"""

from __future__ import annotations

from .algorithm import IdentificationAlgorithm
from .context import (
    AlgorithmContext,
    ExportContext,
    ExportContribution,
    ModuleContext,
    VisualizationRequest,
)
from .descriptors import AlgorithmDescriptor, ModuleDescriptor
from .enums import (
    Aggregation,
    AlgorithmFamily,
    FieldGroup,
    FieldType,
    OverlayKind,
    ROIKind,
    ScoreSemantics,
    Severity,
    StatisticKind,
)
from .fields import FieldDefinition, Validation
from .imaging import ROI, ROISpec, Sample
from .matching import ComparisonResult, FeatureSet, MatchCandidate, RankedResult
from .profile import (
    AlgorithmCompatibility,
    DerivedStatistic,
    ExportFormatSpec,
    ReferenceImage,
    SpeciesProfile,
)
from .species_module import SpeciesModule
from .validation import ValidationIssue, ValidationResult
from .visualization import Color, Overlay, Visualization

__all__ = [  # noqa: RUF022  (grouped by category for readability, not alphabetized)
    # base classes
    "SpeciesModule",
    "IdentificationAlgorithm",
    # descriptors
    "ModuleDescriptor",
    "AlgorithmDescriptor",
    # enums
    "FieldType",
    "FieldGroup",
    "ROIKind",
    "Severity",
    "AlgorithmFamily",
    "ScoreSemantics",
    "Aggregation",
    "StatisticKind",
    "OverlayKind",
    # fields / validation
    "FieldDefinition",
    "Validation",
    "ValidationIssue",
    "ValidationResult",
    # imaging
    "ROI",
    "ROISpec",
    "Sample",
    # profile
    "SpeciesProfile",
    "AlgorithmCompatibility",
    "DerivedStatistic",
    "ExportFormatSpec",
    "ReferenceImage",
    # matching
    "FeatureSet",
    "ComparisonResult",
    "MatchCandidate",
    "RankedResult",
    # visualization
    "Overlay",
    "Visualization",
    "Color",
    # contexts
    "ModuleContext",
    "AlgorithmContext",
    "VisualizationRequest",
    "ExportContext",
    "ExportContribution",
]
