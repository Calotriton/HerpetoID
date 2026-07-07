"""Lightweight plugin descriptors used by the registry for discovery.

These are cheap to construct (a ``@classmethod`` on each plugin) so the registry can enumerate and
display plugins without triggering heavy ``initialize()`` work.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from .enums import AlgorithmFamily, ScoreSemantics


@dataclass(frozen=True, slots=True)
class ModuleDescriptor:
    """Identity of a species module."""

    module_id: str
    name: str
    version: str
    supported_species: tuple[str, ...]  # scientific names (at least one)
    author: str = ""
    description: str = ""
    api_version: str = "1.0"

    def __post_init__(self) -> None:
        if not self.module_id:
            raise ValueError("ModuleDescriptor.module_id must be non-empty")
        if not self.supported_species:
            raise ValueError("ModuleDescriptor.supported_species must list at least one species")


@dataclass(frozen=True, slots=True)
class AlgorithmDescriptor:
    """Identity and capabilities of an identification algorithm."""

    algorithm_id: str
    name: str
    version: str
    family: AlgorithmFamily
    score_semantics: ScoreSemantics = ScoreSemantics.SIMILARITY
    requires_grayscale: bool = False
    needs_gpu: bool = False
    author: str = ""
    description: str = ""
    api_version: str = "1.0"
    #: Describes user-configurable parameters (surfaced in the Algorithm Manager / Settings).
    config_schema: Mapping[str, Any] = field(default_factory=dict)
    default_config: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.algorithm_id:
            raise ValueError("AlgorithmDescriptor.algorithm_id must be non-empty")
