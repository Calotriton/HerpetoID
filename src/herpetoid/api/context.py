"""Runtime contexts passed into plugin methods.

Contexts hand a plugin the small amount of environment it needs (resource paths, merged user config, a
logger, a compute device) without coupling it to concrete Core service classes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from logging import Logger, getLogger
from pathlib import Path
from typing import Any

import numpy as np

from .imaging import Sample


def _module_logger() -> Logger:
    return getLogger("herpetoid.plugin.module")


def _algorithm_logger() -> Logger:
    return getLogger("herpetoid.plugin.algorithm")


@dataclass(slots=True)
class ModuleContext:
    """Context handed to a :class:`SpeciesModule` at ``initialize()``."""

    resource_root: Path | None = None  # directory the module may load bundled resources from
    config: Mapping[str, Any] = field(default_factory=dict)
    logger: Logger = field(default_factory=_module_logger)


@dataclass(slots=True)
class AlgorithmContext:
    """Context handed to an :class:`IdentificationAlgorithm` at ``initialize()``."""

    resource_root: Path | None = None
    config: Mapping[str, Any] = field(default_factory=dict)  # merged user config (thresholds, ...)
    device: str = "cpu"  # 'cpu' | 'cuda' | ...
    logger: Logger = field(default_factory=_algorithm_logger)


@dataclass(slots=True)
class VisualizationRequest:
    """Input to :meth:`SpeciesModule.visualize`."""

    kind: str  # e.g. 'roi', 'preprocess', 'match'
    image: np.ndarray | None = None
    sample: Sample | None = None
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExportContext:
    """Input to :meth:`SpeciesModule.export` — the report/export requesting a contribution."""

    target: str  # exporter id or report-section key
    options: Mapping[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExportContribution:
    """Species-specific content a module contributes to a report/export."""

    rows: Sequence[Mapping[str, Any]] = ()
    sections: Mapping[str, Any] = field(default_factory=dict)
