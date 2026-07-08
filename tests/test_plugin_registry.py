"""Tests for the plugin registry and folder-based discovery (incl. graceful degradation)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from herpetoid import api
from herpetoid.application.registry import PluginConflictError, PluginRegistry
from herpetoid.infrastructure.plugin_discovery import discover_folder


class ModA(api.SpeciesModule):
    @classmethod
    def descriptor(cls) -> api.ModuleDescriptor:
        return api.ModuleDescriptor("mod.a", "Module A", "1.0", ("Aaa aaa",))

    def define_species_profile(self) -> api.SpeciesProfile:
        return api.SpeciesProfile(scientific_name="Aaa aaa")

    def preprocess(self, image: np.ndarray, roi: api.ROI) -> api.Sample:
        return api.Sample(image=np.asarray(image))


class AlgoKp(api.IdentificationAlgorithm):
    @classmethod
    def descriptor(cls) -> api.AlgorithmDescriptor:
        return api.AlgorithmDescriptor("algo.kp", "KP", "1.0", api.AlgorithmFamily.KEYPOINT)

    def extract_features(self, sample: api.Sample) -> api.FeatureSet:
        return api.FeatureSet("algo.kp", api.AlgorithmFamily.KEYPOINT, np.zeros((1, 4)))

    def compare(self, query: api.FeatureSet, target: api.FeatureSet) -> api.ComparisonResult:
        return api.ComparisonResult(1.0, 1.0)


class AlgoEmb(api.IdentificationAlgorithm):
    @classmethod
    def descriptor(cls) -> api.AlgorithmDescriptor:
        return api.AlgorithmDescriptor("algo.emb", "Emb", "1.0", api.AlgorithmFamily.EMBEDDING)

    def extract_features(self, sample: api.Sample) -> api.FeatureSet:
        return api.FeatureSet("algo.emb", api.AlgorithmFamily.EMBEDDING, np.zeros(4))

    def compare(self, query: api.FeatureSet, target: api.FeatureSet) -> api.ComparisonResult:
        return api.ComparisonResult(1.0, 1.0)


def test_register_and_lookup() -> None:
    reg = PluginRegistry()
    reg.register_module(ModA, source="test")
    reg.register_algorithm(AlgoKp, source="test")
    assert reg.module("mod.a") is not None
    assert [m.descriptor.module_id for m in reg.modules()] == ["mod.a"]
    assert reg.modules_for_species("Aaa aaa")
    assert not reg.modules_for_species("Zzz zzz")
    assert isinstance(reg.create_module("mod.a"), api.SpeciesModule)


def test_conflict_and_replace() -> None:
    reg = PluginRegistry()
    reg.register_module(ModA, source="a")
    with pytest.raises(PluginConflictError):
        reg.register_module(ModA, source="b")
    reg.register_module(ModA, source="b", replace=True)  # replace is allowed


def test_capability_matching() -> None:
    reg = PluginRegistry()
    reg.register_algorithm(AlgoKp, source="t")
    reg.register_algorithm(AlgoEmb, source="t")
    keypoint_only = api.AlgorithmCompatibility(families=(api.AlgorithmFamily.KEYPOINT,))
    assert [a.descriptor.algorithm_id for a in reg.algorithms_for(keypoint_only)] == ["algo.kp"]
    both_but_deny = api.AlgorithmCompatibility(
        families=(api.AlgorithmFamily.KEYPOINT, api.AlgorithmFamily.EMBEDDING),
        deny_ids=("algo.emb",),
    )
    assert {a.descriptor.algorithm_id for a in reg.algorithms_for(both_but_deny)} == {"algo.kp"}


def test_enable_disable() -> None:
    reg = PluginRegistry()
    reg.register_algorithm(AlgoKp, source="t")
    assert reg.is_algorithm_enabled("algo.kp")
    reg.set_algorithm_enabled("algo.kp", False)
    assert not reg.is_algorithm_enabled("algo.kp")
    assert reg.algorithms(enabled_only=True) == []
    assert len(reg.algorithms()) == 1  # still registered, just disabled
    reg.set_algorithm_enabled("algo.kp", True)
    assert reg.algorithms(enabled_only=True)


def test_create_unknown_raises() -> None:
    with pytest.raises(KeyError):
        PluginRegistry().create_module("nope")


_PLUGIN_SOURCE = """
import numpy as np
from herpetoid import api


class FolderModule(api.SpeciesModule):
    @classmethod
    def descriptor(cls):
        return api.ModuleDescriptor("MOD_ID", "Folder Module", "1.0", ("Folderus folderus",))

    def define_species_profile(self):
        return api.SpeciesProfile(scientific_name="Folderus folderus")

    def preprocess(self, image, roi):
        return api.Sample(image=np.asarray(image))


class FolderAlgo(api.IdentificationAlgorithm):
    @classmethod
    def descriptor(cls):
        return api.AlgorithmDescriptor("ALGO_ID", "Folder Algo", "1.0", api.AlgorithmFamily.KEYPOINT)

    def extract_features(self, sample):
        return api.FeatureSet("ALGO_ID", api.AlgorithmFamily.KEYPOINT, np.zeros((1, 4)))

    def compare(self, query, target):
        return api.ComparisonResult(1.0, 1.0)
"""


def test_folder_discovery(tmp_path: Path) -> None:
    source = _PLUGIN_SOURCE.replace("MOD_ID", "folder.mod").replace("ALGO_ID", "folder.algo")
    (tmp_path / "goodplugin.py").write_text(source)
    reg = PluginRegistry()
    discover_folder(reg, tmp_path)
    assert reg.module("folder.mod") is not None
    assert reg.algorithm("folder.algo") is not None
    assert isinstance(reg.create_module("folder.mod"), api.SpeciesModule)


def test_folder_discovery_is_graceful(tmp_path: Path) -> None:
    # A plugin that fails to import must be skipped, not crash discovery of the good one.
    (tmp_path / "brokenplugin.py").write_text("import a_module_that_does_not_exist_xyz\n")
    good = _PLUGIN_SOURCE.replace("MOD_ID", "folder.mod2").replace("ALGO_ID", "folder.algo2")
    (tmp_path / "workingplugin.py").write_text(good)
    reg = PluginRegistry()
    discover_folder(reg, tmp_path)  # must not raise
    assert reg.module("folder.mod2") is not None
    assert reg.algorithm("folder.algo2") is not None
