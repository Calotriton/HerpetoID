"""Plugin discovery: populate a :class:`PluginRegistry` from the two supported sources.

1. **Entry points** -- ``herpetoid.species_modules`` and ``herpetoid.algorithms`` groups, for
   pip-installed / first-party plugins.
2. **Drop-in folder** -- a user ``plugins/`` directory of Python modules/packages, for non-technical
   installation.

Every plugin is loaded in isolation: a plugin that fails to import or register is logged and skipped,
never bringing down discovery (the "graceful degradation" behaviour).
"""

from __future__ import annotations

import contextlib
import importlib
import inspect
import sys
from importlib.metadata import entry_points
from logging import Logger, getLogger
from pathlib import Path
from types import ModuleType

from herpetoid.api import IdentificationAlgorithm, SpeciesModule
from herpetoid.application.registry import PluginRegistry

MODULE_GROUP = "herpetoid.species_modules"
ALGORITHM_GROUP = "herpetoid.algorithms"

_DEFAULT_LOGGER = getLogger("herpetoid.plugins")


def discover_entry_points(registry: PluginRegistry, *, logger: Logger | None = None) -> None:
    """Register plugins advertised via Python entry points."""
    log = logger or _DEFAULT_LOGGER
    for entry in entry_points(group=MODULE_GROUP):
        try:
            registry.register_module(entry.load(), source=f"entry_point:{entry.name}", replace=True)
        except (
            Exception
        ) as exc:  # isolate per-plugin failures so one bad plugin cannot break discovery
            log.warning("Could not load species-module entry point %r: %s", entry.name, exc)
    for entry in entry_points(group=ALGORITHM_GROUP):
        try:
            registry.register_algorithm(
                entry.load(), source=f"entry_point:{entry.name}", replace=True
            )
        except Exception as exc:  # isolate per-plugin failures
            log.warning("Could not load algorithm entry point %r: %s", entry.name, exc)


def discover_folder(
    registry: PluginRegistry, folder: Path, *, logger: Logger | None = None
) -> None:
    """Register plugins from a drop-in ``plugins/`` folder of Python modules/packages."""
    log = logger or _DEFAULT_LOGGER
    if not folder.is_dir():
        return
    folder_str = str(folder)
    added = folder_str not in sys.path
    if added:
        sys.path.insert(0, folder_str)
    try:
        for entry in sorted(folder.iterdir()):
            name = _plugin_module_name(entry)
            if name is None:
                continue
            try:
                module = importlib.import_module(name)
            except Exception as exc:  # isolate per-plugin failures
                log.warning("Could not import folder plugin %r: %s", entry.name, exc)
                continue
            _register_from_module(registry, module, source=f"folder:{entry.name}", logger=log)
    finally:
        if added:
            with contextlib.suppress(ValueError):
                sys.path.remove(folder_str)


def _plugin_module_name(entry: Path) -> str | None:
    """The importable module name for a folder entry, or ``None`` if it is not a plugin."""
    if entry.is_dir() and (entry / "__init__.py").exists():
        return entry.name
    if entry.suffix == ".py" and not entry.name.startswith("_"):
        return entry.stem
    return None


def _register_from_module(
    registry: PluginRegistry, module: ModuleType, *, source: str, logger: Logger
) -> None:
    """Register every concrete plugin class *defined in* ``module``."""
    for value in vars(module).values():
        if not isinstance(value, type) or value.__module__ != module.__name__:
            continue
        if inspect.isabstract(value):
            continue
        try:
            if issubclass(value, SpeciesModule) and value is not SpeciesModule:
                registry.register_module(value, source=source, replace=True)
            elif (
                issubclass(value, IdentificationAlgorithm) and value is not IdentificationAlgorithm
            ):
                registry.register_algorithm(value, source=source, replace=True)
        except Exception as exc:  # isolate per-plugin failures
            logger.warning("Could not register plugin %r from %s: %s", value.__name__, source, exc)
