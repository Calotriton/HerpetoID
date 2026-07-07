"""The abstract base class every species plugin inherits from.

Design (see the implementation plan, Prompts 4 & 8):

* **Strictly abstract** (a module must implement): :meth:`descriptor`, :meth:`define_species_profile`,
  :meth:`preprocess`.
* **Defaulted** (override only if needed): :meth:`initialize`, :meth:`define_observation_fields` and
  :meth:`compatible_algorithms` (views onto the profile — single source of truth), :meth:`select_roi`,
  :meth:`validate_image`, :meth:`visualize`, :meth:`export`.

Returns are Qt-free declarative data only. A module never builds GUI widgets.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from .context import ExportContext, ExportContribution, ModuleContext, VisualizationRequest
from .descriptors import ModuleDescriptor
from .fields import FieldDefinition
from .imaging import ROI, Sample
from .profile import AlgorithmCompatibility, SpeciesProfile
from .validation import ValidationIssue, ValidationResult
from .visualization import Visualization


class SpeciesModule(ABC):
    """Base class for a per-taxon plugin."""

    @classmethod
    @abstractmethod
    def descriptor(cls) -> ModuleDescriptor:
        """Lightweight identity for the registry (must not trigger heavy initialization)."""

    def initialize(self, ctx: ModuleContext) -> None:
        """Optional one-time setup (load bundled resources / models). Default: no-op."""

    # -- declarative manifest -------------------------------------------------------------------
    @abstractmethod
    def define_species_profile(self) -> SpeciesProfile:
        """Return the declarative :class:`SpeciesProfile` (Core renders forms/panels/stats/exports)."""

    def define_observation_fields(self) -> tuple[FieldDefinition, ...]:
        """Species-specific fields. Default: the profile's ``measurements`` (single source of truth)."""
        return tuple(self.define_species_profile().measurements)

    def compatible_algorithms(self) -> AlgorithmCompatibility:
        """Which algorithm families this module's :class:`Sample` suits. Default: from the profile."""
        return self.define_species_profile().compatible_algorithms

    # -- image processing -----------------------------------------------------------------------
    @abstractmethod
    def preprocess(self, image: np.ndarray, roi: ROI) -> Sample:
        """Normalize the ROI of ``image`` into a standardized :class:`Sample` for algorithms."""

    def select_roi(self, image: np.ndarray, ctx: ModuleContext | None = None) -> ROI:
        """Auto-suggest an ROI. Default: full image; the GUI lets the user draw/adjust the final ROI."""
        return ROI.full_image()

    def validate_image(
        self, image: np.ndarray, ctx: ModuleContext | None = None
    ) -> ValidationResult:
        """Basic image-quality gate. Default: reject empty / wrong-dimensioned images."""
        issues: list[ValidationIssue] = []
        if image is None or getattr(image, "size", 0) == 0:
            issues.append(ValidationIssue("empty", "The image is empty."))
        elif image.ndim not in (2, 3):
            issues.append(ValidationIssue("shape", "Unsupported image shape."))
        return ValidationResult.of(issues)

    # -- presentation / export ------------------------------------------------------------------
    def visualize(self, request: VisualizationRequest) -> Visualization:
        """Overlay data for a view (ROI, landmarks, ...). Default: nothing."""
        return Visualization.empty()

    def export(self, ctx: ExportContext) -> ExportContribution:
        """Species-specific content for a report/export. Default: no contribution."""
        return ExportContribution()
