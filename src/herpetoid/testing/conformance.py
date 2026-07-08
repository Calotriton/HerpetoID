"""Reusable conformance test suites for HerpetoID plugins.

Subclass these in a test module (class name starting with ``Test``) and implement the factory method;
pytest then runs the inherited checks against your plugin. Shipped inside the package so that external
plugin authors can validate their species modules and algorithms exactly the way HerpetoID does::

    from herpetoid.testing import SpeciesModuleContract

    class TestMyModule(SpeciesModuleContract):
        def make_module(self):
            return MyModule()
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from herpetoid.api import (
    ROI,
    AlgorithmCompatibility,
    AlgorithmDescriptor,
    ComparisonResult,
    FeatureSet,
    FieldDefinition,
    IdentificationAlgorithm,
    ModuleDescriptor,
    RankedResult,
    Sample,
    SpeciesModule,
    SpeciesProfile,
    ValidationResult,
)


class SpeciesModuleContract:
    """Checks every :class:`~herpetoid.api.SpeciesModule` implementation must satisfy."""

    def make_module(self) -> SpeciesModule:
        raise NotImplementedError

    def _image(self) -> np.ndarray:
        return np.random.default_rng(0).integers(0, 256, size=(48, 64), dtype=np.uint8)

    def test_descriptor_wellformed(self) -> None:
        descriptor = type(self.make_module()).descriptor()
        assert isinstance(descriptor, ModuleDescriptor)
        assert descriptor.module_id
        assert descriptor.version
        assert descriptor.supported_species

    def test_profile_wellformed(self) -> None:
        profile = self.make_module().define_species_profile()
        assert isinstance(profile, SpeciesProfile)
        assert profile.scientific_name

    def test_observation_fields_unique(self) -> None:
        fields = self.make_module().define_observation_fields()
        assert all(isinstance(f, FieldDefinition) for f in fields)
        keys = [f.key for f in fields]
        assert len(keys) == len(set(keys)), "observation field keys must be unique"

    def test_compatible_algorithms(self) -> None:
        compat = self.make_module().compatible_algorithms()
        assert isinstance(compat, AlgorithmCompatibility)
        assert compat.families, "a module must declare at least one compatible algorithm family"

    def test_select_roi_returns_roi(self) -> None:
        assert isinstance(self.make_module().select_roi(self._image()), ROI)

    def test_preprocess_returns_valid_sample(self) -> None:
        module = self.make_module()
        image = self._image()
        sample = module.preprocess(image, module.select_roi(image))
        assert isinstance(sample, Sample)
        assert sample.image.ndim in (2, 3)
        if sample.roi_mask is not None:
            assert sample.roi_mask.shape[:2] == sample.image.shape[:2]

    def test_validate_image_returns_result(self) -> None:
        assert isinstance(self.make_module().validate_image(self._image()), ValidationResult)


class AlgorithmContract:
    """Checks every :class:`~herpetoid.api.IdentificationAlgorithm` implementation must satisfy."""

    def make_algorithm(self) -> IdentificationAlgorithm:
        raise NotImplementedError

    def _sample(self) -> Sample:
        # 192x192 so keypoint algorithms (which ignore image borders) have room to detect features.
        rng = np.random.default_rng(1)
        return Sample(image=rng.integers(0, 256, size=(192, 192), dtype=np.uint8))

    def test_descriptor_wellformed(self) -> None:
        descriptor = type(self.make_algorithm()).descriptor()
        assert isinstance(descriptor, AlgorithmDescriptor)
        assert descriptor.algorithm_id
        assert descriptor.version

    def test_extract_features(self) -> None:
        features = self.make_algorithm().extract_features(self._sample())
        assert isinstance(features, FeatureSet)
        assert features.descriptors.size > 0

    def test_compare_normalized_range(self) -> None:
        algo = self.make_algorithm()
        features = algo.extract_features(self._sample())
        result = algo.compare(features, features)
        assert isinstance(result, ComparisonResult)
        assert 0.0 <= result.normalized_score <= 1.0

    def test_self_match_is_strong(self) -> None:
        algo = self.make_algorithm()
        features = algo.extract_features(self._sample())
        result = algo.compare(features, features)
        assert result.normalized_score >= 0.5, "an identical sample should self-match strongly"

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        algo = self.make_algorithm()
        features = algo.extract_features(self._sample())
        features.ref = "ref:1"
        path = tmp_path / "features.npz"
        algo.save_features(features, path)
        loaded = algo.load_features(path)
        assert np.array_equal(np.asarray(features.descriptors), np.asarray(loaded.descriptors))
        assert loaded.algorithm_id == features.algorithm_id
        assert loaded.ref == "ref:1"

    def test_rank_is_ordered(self) -> None:
        algo = self.make_algorithm()
        query = algo.extract_features(self._sample())
        candidates: list[FeatureSet] = []
        for index in range(3):
            features = algo.extract_features(self._sample())
            features.ref = f"c:{index}"
            candidates.append(features)
        result = algo.rank(query, candidates)
        assert isinstance(result, RankedResult)
        assert len(result.candidates) == 3
        assert [candidate.rank for candidate in result.candidates] == [1, 2, 3]
        scores = [candidate.normalized_score for candidate in result.candidates]
        assert scores == sorted(scores, reverse=True)
