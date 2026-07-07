"""Testing utilities shipped with HerpetoID.

Re-exports the reusable plugin conformance suites so both HerpetoID's own tests and third-party plugin
authors can validate implementations against the SDK contract.
"""

from __future__ import annotations

from .conformance import AlgorithmContract, SpeciesModuleContract

__all__ = ["AlgorithmContract", "SpeciesModuleContract"]
