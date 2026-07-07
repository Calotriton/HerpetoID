"""Self-test of the reusable conformance suites against minimal in-test fake plugins.

This proves both that the suites work and that a trivial, correct plugin satisfies the SDK contract —
the same suites real plugins (ORB, Calotriton asper) will be validated against.
"""

from __future__ import annotations

import numpy as np

from herpetoid import api
from herpetoid.testing import AlgorithmContract, SpeciesModuleContract


class _FakeModule(api.SpeciesModule):
    @classmethod
    def descriptor(cls) -> api.ModuleDescriptor:
        return api.ModuleDescriptor("fake", "Fake Newt", "1.0", ("Fakus fakus",))

    def define_species_profile(self) -> api.SpeciesProfile:
        return api.SpeciesProfile(
            scientific_name="Fakus fakus",
            common_name="Fake newt",
            measurements=(api.FieldDefinition("length", "Length", api.FieldType.FLOAT, unit="mm"),),
        )

    def preprocess(self, image: np.ndarray, roi: api.ROI) -> api.Sample:
        box = roi.bounding_box()
        if box is not None:
            x, y, w, h = box
            image = image[y : y + h, x : x + w]
        return api.Sample(image=np.asarray(image), color_space="gray")


class _FakeAlgorithm(api.IdentificationAlgorithm):
    @classmethod
    def descriptor(cls) -> api.AlgorithmDescriptor:
        return api.AlgorithmDescriptor("fake", "Fake Cosine", "1.0", api.AlgorithmFamily.EMBEDDING)

    def extract_features(self, sample: api.Sample) -> api.FeatureSet:
        vector = sample.image.astype(np.float32).ravel()
        return api.FeatureSet("fake", api.AlgorithmFamily.EMBEDDING, vector)

    def compare(self, query: api.FeatureSet, target: api.FeatureSet) -> api.ComparisonResult:
        a = np.asarray(query.descriptors, dtype=np.float64).ravel()
        b = np.asarray(target.descriptors, dtype=np.float64).ravel()
        size = min(a.size, b.size)
        if size == 0:
            return api.ComparisonResult(0.0, 0.0)
        a, b = a[:size], b[:size]
        denom = float(np.linalg.norm(a) * np.linalg.norm(b)) or 1.0
        cosine = float(np.dot(a, b) / denom)
        return api.ComparisonResult(
            score=cosine, normalized_score=max(0.0, min(1.0, (cosine + 1.0) / 2.0))
        )


class TestFakeModuleConformance(SpeciesModuleContract):
    def make_module(self) -> api.SpeciesModule:
        return _FakeModule()


class TestFakeAlgorithmConformance(AlgorithmContract):
    def make_algorithm(self) -> api.IdentificationAlgorithm:
        return _FakeAlgorithm()
