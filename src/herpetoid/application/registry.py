"""The plugin registry.

Holds the discovered species modules and identification algorithms (by their lightweight descriptors),
answers lookup and capability-matching queries, tracks enabled/disabled state, and instantiates plugins
on demand. Discovery (entry points + drop-in folder) lives in the infrastructure layer and populates a
registry via :meth:`register_module` / :meth:`register_algorithm`.
"""

from __future__ import annotations

from dataclasses import dataclass

from herpetoid.api import (
    AlgorithmCompatibility,
    AlgorithmDescriptor,
    IdentificationAlgorithm,
    ModuleDescriptor,
    SpeciesModule,
)
from herpetoid.domain import PluginRef


class PluginConflictError(Exception):
    """Raised when registering a plugin whose id is already registered (without ``replace``)."""


@dataclass(frozen=True, slots=True)
class RegisteredModule:
    """A registered species module: its descriptor, class, and where it came from."""

    descriptor: ModuleDescriptor
    plugin_class: type[SpeciesModule]
    source: str


@dataclass(frozen=True, slots=True)
class RegisteredAlgorithm:
    """A registered identification algorithm: its descriptor, class, and where it came from."""

    descriptor: AlgorithmDescriptor
    plugin_class: type[IdentificationAlgorithm]
    source: str


def _algorithm_matches(descriptor: AlgorithmDescriptor, compat: AlgorithmCompatibility) -> bool:
    """Whether an algorithm satisfies a module's capability declaration."""
    if compat.allow_ids and descriptor.algorithm_id not in compat.allow_ids:
        return False
    if descriptor.algorithm_id in compat.deny_ids:
        return False
    return descriptor.family in compat.families


class PluginRegistry:
    """In-memory registry of species modules and identification algorithms."""

    def __init__(self) -> None:
        self._modules: dict[str, RegisteredModule] = {}
        self._algorithms: dict[str, RegisteredAlgorithm] = {}
        self._disabled_modules: set[str] = set()
        self._disabled_algorithms: set[str] = set()

    # -- registration ---------------------------------------------------------------------------
    def register_module(
        self, plugin_class: type[SpeciesModule], *, source: str, replace: bool = False
    ) -> RegisteredModule:
        descriptor = plugin_class.descriptor()
        existing = self._modules.get(descriptor.module_id)
        if existing is not None and not replace:
            raise PluginConflictError(
                f"species module id {descriptor.module_id!r} already registered "
                f"from {existing.source!r}"
            )
        record = RegisteredModule(descriptor, plugin_class, source)
        self._modules[descriptor.module_id] = record
        return record

    def register_algorithm(
        self, plugin_class: type[IdentificationAlgorithm], *, source: str, replace: bool = False
    ) -> RegisteredAlgorithm:
        descriptor = plugin_class.descriptor()
        existing = self._algorithms.get(descriptor.algorithm_id)
        if existing is not None and not replace:
            raise PluginConflictError(
                f"algorithm id {descriptor.algorithm_id!r} already registered "
                f"from {existing.source!r}"
            )
        record = RegisteredAlgorithm(descriptor, plugin_class, source)
        self._algorithms[descriptor.algorithm_id] = record
        return record

    # -- lookups --------------------------------------------------------------------------------
    def modules(self, *, enabled_only: bool = False) -> list[RegisteredModule]:
        records = list(self._modules.values())
        if enabled_only:
            records = [r for r in records if self.is_module_enabled(r.descriptor.module_id)]
        return sorted(records, key=lambda r: r.descriptor.module_id)

    def algorithms(self, *, enabled_only: bool = False) -> list[RegisteredAlgorithm]:
        records = list(self._algorithms.values())
        if enabled_only:
            records = [r for r in records if self.is_algorithm_enabled(r.descriptor.algorithm_id)]
        return sorted(records, key=lambda r: r.descriptor.algorithm_id)

    def module(self, module_id: str) -> RegisteredModule | None:
        return self._modules.get(module_id)

    def algorithm(self, algorithm_id: str) -> RegisteredAlgorithm | None:
        return self._algorithms.get(algorithm_id)

    def species_offered(self) -> dict[str, PluginRef]:
        """Every species an enabled module handles, mapped to the module that handles it.

        Where two modules claim the same species the first by module id wins, matching what the
        import screen offers — so the species a user can pick and the module that will interpret it
        are decided in exactly one place.
        """
        offered: dict[str, PluginRef] = {}
        for record in self.modules(enabled_only=True):
            for name in record.descriptor.supported_species:
                offered.setdefault(
                    name, PluginRef(record.descriptor.module_id, record.descriptor.version)
                )
        return offered

    def modules_for_species(self, scientific_name: str) -> list[RegisteredModule]:
        return [
            r
            for r in self.modules(enabled_only=True)
            if scientific_name in r.descriptor.supported_species
        ]

    def algorithms_for(
        self, compat: AlgorithmCompatibility, *, enabled_only: bool = True
    ) -> list[RegisteredAlgorithm]:
        """Algorithms whose capabilities satisfy a module's compatibility declaration."""
        return [
            r
            for r in self.algorithms(enabled_only=enabled_only)
            if _algorithm_matches(r.descriptor, compat)
        ]

    # -- enable / disable -----------------------------------------------------------------------
    def is_module_enabled(self, module_id: str) -> bool:
        return module_id not in self._disabled_modules

    def is_algorithm_enabled(self, algorithm_id: str) -> bool:
        return algorithm_id not in self._disabled_algorithms

    def set_module_enabled(self, module_id: str, enabled: bool) -> None:
        if enabled:
            self._disabled_modules.discard(module_id)
        else:
            self._disabled_modules.add(module_id)

    def set_algorithm_enabled(self, algorithm_id: str, enabled: bool) -> None:
        if enabled:
            self._disabled_algorithms.discard(algorithm_id)
        else:
            self._disabled_algorithms.add(algorithm_id)

    # -- instantiation --------------------------------------------------------------------------
    def create_module(self, module_id: str) -> SpeciesModule:
        record = self._modules.get(module_id)
        if record is None:
            raise KeyError(f"no species module registered with id {module_id!r}")
        return record.plugin_class()

    def create_algorithm(self, algorithm_id: str) -> IdentificationAlgorithm:
        record = self._algorithms.get(algorithm_id)
        if record is None:
            raise KeyError(f"no algorithm registered with id {algorithm_id!r}")
        return record.plugin_class()
