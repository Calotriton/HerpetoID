"""Tests for the first-party plugins (ORB algorithm + the species modules).

Includes the reusable conformance suites run against the real plugins, and an end-to-end
identification pipeline that must rank the same individual above different ones.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
import pytest

from herpetoid import api
from herpetoid.application.registry import PluginRegistry
from herpetoid.infrastructure.plugin_discovery import discover_entry_points
from herpetoid.plugins.algorithms.orb import OrbAlgorithm
from herpetoid.plugins.algorithms.orb.algorithm import inlier_score
from herpetoid.plugins.algorithms.sift import SiftLnbnnAlgorithm
from herpetoid.plugins.algorithms.sift.algorithm import lnbnn_score
from herpetoid.plugins.species.calotriton_asper import CalotritonAsperModule
from herpetoid.plugins.species.salamandra_salamandra import SalamandraSalamandraModule
from herpetoid.testing import AlgorithmContract, SpeciesModuleContract


@pytest.fixture(autouse=True)
def _deterministic_cv() -> None:
    cv2.setRNGSeed(12345)


def _spot_pattern(seed: int, size: int = 256, count: int = 45) -> np.ndarray:
    """A synthetic 'ventral pattern': dark ellipses (spots) on a pale ground."""
    rng = np.random.default_rng(seed)
    image = np.full((size, size), 255, dtype=np.uint8)
    for _ in range(count):
        cx, cy = rng.integers(20, size - 20, size=2)
        ax, ay = rng.integers(5, 15, size=2)
        angle = int(rng.integers(0, 180))
        cv2.ellipse(image, (int(cx), int(cy)), (int(ax), int(ay)), angle, 0, 360, 0, -1)
    return image


def _rotate(image: np.ndarray, degrees: float) -> np.ndarray:
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), degrees, 1.0)
    return cv2.warpAffine(image, matrix, (w, h), borderValue=255)


class TestOrbConformance(AlgorithmContract):
    def make_algorithm(self) -> api.IdentificationAlgorithm:
        return OrbAlgorithm()


class TestCalotritonConformance(SpeciesModuleContract):
    def make_module(self) -> api.SpeciesModule:
        return CalotritonAsperModule()


def test_calotriton_profile() -> None:
    profile = CalotritonAsperModule().define_species_profile()
    assert profile.scientific_name == "Calotriton asper"
    assert profile.pattern_region == "ventral"
    assert {f.key for f in profile.measurements} == {"svl", "weight", "sex", "life_stage"}
    assert api.AlgorithmFamily.KEYPOINT in profile.compatible_algorithms.families
    assert {s.key for s in profile.derived_statistics} >= {"mean_svl", "sex_ratio", "svl_growth"}


def test_preprocess_produces_grayscale_sample() -> None:
    sample = CalotritonAsperModule().preprocess(_spot_pattern(1), api.ROI.full_image())
    assert sample.is_grayscale
    assert sample.image.dtype == np.uint8


def test_identification_pipeline_discriminates() -> None:
    module = CalotritonAsperModule(config={"denoise": False})
    algo = OrbAlgorithm()
    roi = api.ROI.full_image()

    query_image = _spot_pattern(1)
    query = algo.extract_features(module.preprocess(query_image, roi))
    assert query.descriptors.shape[0] > 10  # features were found

    # same individual, rotated -> should match strongly
    same = algo.extract_features(module.preprocess(_rotate(query_image, 12), roi))
    same_result = algo.compare(query, same)

    # a different individual -> weaker match
    other = algo.extract_features(module.preprocess(_spot_pattern(777), roi))
    other_result = algo.compare(query, other)

    assert same_result.inliers > other_result.inliers
    assert same_result.normalized_score > other_result.normalized_score


def test_rank_puts_same_individual_first() -> None:
    module = CalotritonAsperModule(config={"denoise": False})
    algo = OrbAlgorithm()
    roi = api.ROI.full_image()

    query_image = _spot_pattern(1)
    query = algo.extract_features(module.preprocess(query_image, roi))

    same = algo.extract_features(module.preprocess(_rotate(query_image, 8), roi))
    same.ref = "same-individual"
    candidates = [same]
    for i in range(3):
        other = algo.extract_features(module.preprocess(_spot_pattern(100 + i), roi))
        other.ref = f"other-{i}"
        candidates.append(other)

    ranked = algo.rank(query, candidates)
    assert ranked.candidates[0].target_ref == "same-individual"


def test_orb_score_bands_follow_the_calibration() -> None:
    """The interface colours a score green at 0.5 and amber at 0.25, so those must mean something.

    On the owner's verified fire-salamander pairs (104 recaptures, 363 look-alike different animals),
    an exhaustive search found that green at eight agreeing matches was right only 22% of the time;
    the false greens sat at 8-9 matches. Green at ten was right 67% of the time (v1.3). Amber starts
    at six, where most recaptures already are.
    """
    config = OrbAlgorithm.descriptor().default_config

    def score(n: int) -> float:
        return inlier_score(n, config["chance_inliers"], config["inlier_scale"])

    assert score(0) == score(3) == 0.0  # what chance produces earns nothing
    assert score(5) < 0.25 <= score(6)
    assert score(9) < 0.5 <= score(10)  # nine agreeing matches is not a strong candidate
    assert score(60) > 0.99
    assert all(score(n) < score(n + 1) for n in range(5, 60))


def _feature_set(descriptors: np.ndarray, points: np.ndarray) -> api.FeatureSet:
    geometry = np.hstack(
        [points, np.full((len(points), 1), 31.0), np.zeros((len(points), 1))]
    ).astype(np.float32)
    return api.FeatureSet("orb", api.AlgorithmFamily.KEYPOINT, descriptors, geometry)


def test_orb_few_agreeing_matches_do_not_look_like_a_strong_match() -> None:
    """Regression: ORB 1.0 scored six agreeing matches out of six at 0.6, a "Strong match".

    It averaged the inlier count with the inlier *ratio*, and a handful of matches that all agree
    has a perfect ratio. On real verified pairs the ratio told recaptures from different animals no
    better than chance (AUC 0.53), and six agreeing matches is what different animals often reach.
    """
    rng = np.random.default_rng(5)
    shared = rng.integers(0, 256, size=(6, 32), dtype=np.uint8)
    query_points = rng.uniform(50, 450, size=(206, 2)).astype(np.float32)
    target_points = rng.uniform(50, 450, size=(206, 2)).astype(np.float32)
    turn = np.deg2rad(20.0)
    similarity = 1.1 * np.array([[np.cos(turn), -np.sin(turn)], [np.sin(turn), np.cos(turn)]])
    target_points[:6] = query_points[:6] @ similarity.T + np.array([30.0, -10.0])
    query = _feature_set(
        np.vstack([shared, rng.integers(0, 256, size=(200, 32), dtype=np.uint8)]), query_points
    )
    target = _feature_set(
        np.vstack([shared, rng.integers(0, 256, size=(200, 32), dtype=np.uint8)]), target_points
    )

    result = OrbAlgorithm().compare(query, target)

    assert result.meta["good_matches"] == 6 and result.inliers == 6
    assert result.inlier_ratio == 1.0  # the old formula's half-score for free
    assert 0.25 <= result.normalized_score < 0.5  # worth a look, not a strong match


def test_orb_many_to_one_matches_cannot_fake_a_strong_match() -> None:
    """Regression: ORB 1.1 scored ~1.0 when many query keypoints matched ONE target keypoint.

    A similarity transform with scale ~0 maps every query point onto that single point, so RANSAC
    counted them all as agreeing. When a whole collection was searched, different animals reached 34
    such "inliers" and were shown green. Matches must be one-to-one, and a fit that collapses the
    pattern is no match.
    """
    rng = np.random.default_rng(11)
    blob = rng.integers(0, 256, size=(1, 32), dtype=np.uint8)
    near_copies = np.repeat(blob, 30, axis=0)
    for row, column in enumerate(rng.integers(0, 32, size=30)):
        near_copies[row, column] ^= 1  # one bit off: each still matches the blob, far below the rest
    query = _feature_set(
        np.vstack([near_copies, rng.integers(0, 256, size=(170, 32), dtype=np.uint8)]),
        rng.uniform(50, 450, size=(200, 2)).astype(np.float32),
    )
    target = _feature_set(
        np.vstack([blob, rng.integers(0, 256, size=(199, 32), dtype=np.uint8)]),
        rng.uniform(50, 450, size=(200, 2)).astype(np.float32),
    )

    result = OrbAlgorithm().compare(query, target)

    assert result.normalized_score < 0.25
    assert result.inliers < 6


def test_orb_tolerance_follows_region_size() -> None:
    """The same capture at twice the resolution must match as convincingly.

    The RANSAC tolerance is a fraction of the matched region, not a pixel count, so a full-resolution
    crop is not held to a stricter standard than a thumbnail.
    """
    module = CalotritonAsperModule(config={"denoise": False})
    algorithm = OrbAlgorithm()
    roi = api.ROI.full_image()
    small = _spot_pattern(1)
    large = cv2.resize(small, (512, 512), interpolation=cv2.INTER_LINEAR)
    results = []
    for image in (small, large):
        query = algorithm.extract_features(module.preprocess(image, roi))
        turned = algorithm.extract_features(module.preprocess(_rotate(image, 12), roi))
        results.append(algorithm.compare(query, turned))
    assert results[1].meta["tolerance_px"] > 1.5 * results[0].meta["tolerance_px"]
    assert all(result.normalized_score >= 0.5 for result in results)


class TestSiftLnbnnConformance(AlgorithmContract):
    def make_algorithm(self) -> api.IdentificationAlgorithm:
        return SiftLnbnnAlgorithm()


def test_sift_score_bands_follow_the_closed_set_calibration() -> None:
    """Green and amber must mean what the closed-set benchmark measured.

    On 69 photographs grouped by eye (12 true recaptures among 2346 pairs), a raw distinctiveness
    weight of ~1.0 was reached by 5 of 12 recaptures and only 4 of 2334 different pairs; ~0.5 by 6 of
    12 and 86 of 2334. So green sits at 1.0 and amber at 0.5.
    """
    config = SiftLnbnnAlgorithm.descriptor().default_config

    def score(weight: float) -> float:
        return lnbnn_score(weight, config["chance_score"], config["score_scale"])

    assert score(0.0) == score(config["chance_score"]) == 0.0
    assert score(0.3) < 0.25 <= score(0.5)
    assert score(0.9) < 0.5 <= score(1.0)
    assert score(6.0) > 0.99
    assert all(score(w) < score(w + 0.1) for w in np.arange(0.2, 5.0, 0.1))


def test_sift_rank_puts_the_recapture_first() -> None:
    """The catalog-wide ranking, which is where this algorithm's evidence comes from."""
    module = SalamandraSalamandraModule()
    algorithm = SiftLnbnnAlgorithm()
    roi = _body_roi()
    animal = _fire_salamander(11)

    query = algorithm.extract_features(
        module.preprocess(_field_capture(animal, np.random.default_rng(1)), roi)
    )
    catalog = []
    for index, seed in enumerate((11, 21, 22, 23)):
        features = algorithm.extract_features(
            module.preprocess(_field_capture(_fire_salamander(seed), np.random.default_rng(2)), roi)
        )
        features.ref = "same-individual" if index == 0 else f"other-{index}"
        catalog.append(features)

    ranked = algorithm.rank(query, catalog)

    assert ranked.candidates[0].target_ref == "same-individual"
    assert ranked.candidates[0].normalized_score > ranked.candidates[1].normalized_score
    assert all(0.0 <= c.normalized_score <= 1.0 for c in ranked.candidates)


def test_sift_rank_survives_a_catalog_it_cannot_score() -> None:
    """A fresh project has almost nothing to be distinctive against; ranking must still return."""
    algorithm = SiftLnbnnAlgorithm()
    empty = api.FeatureSet("sift_lnbnn", api.AlgorithmFamily.KEYPOINT, np.empty((0, 128), np.float32),
                           np.empty((0, 4), np.float32))
    empty.ref = "no-features"
    query = algorithm.extract_features(
        SalamandraSalamandraModule().preprocess(_fire_salamander(12), _body_roi())
    )

    ranked = algorithm.rank(query, [empty])

    assert [c.target_ref for c in ranked.candidates] == ["no-features"]
    assert ranked.candidates[0].normalized_score == 0.0


def test_sift_rank_is_reproducible() -> None:
    """Regression: the first cut searched approximately, and the scores wandered between runs.

    With FLANN's default search, 247 of the 2346 pairs in the owner's closed-set benchmark changed
    colour band from one run to the next, and the count of different animals shown green wandered
    between 2 and 8. A score a researcher cannot reproduce is not evidence, so the search is exact.
    """
    module = SalamandraSalamandraModule()
    algorithm = SiftLnbnnAlgorithm()
    roi = _body_roi()
    query = algorithm.extract_features(
        module.preprocess(_field_capture(_fire_salamander(11), np.random.default_rng(1)), roi)
    )
    catalog = []
    for index, seed in enumerate((11, 21, 22)):
        features = algorithm.extract_features(
            module.preprocess(_field_capture(_fire_salamander(seed), np.random.default_rng(2)), roi)
        )
        features.ref = f"candidate-{index}"
        catalog.append(features)

    cv2.setRNGSeed(1)
    first = {c.target_ref: c.normalized_score for c in algorithm.rank(query, catalog).candidates}
    cv2.setRNGSeed(9_999)
    second = {c.target_ref: c.normalized_score for c in algorithm.rank(query, catalog).candidates}

    assert first == second


def _newt_belly(seed: int, background_seed: int | None = None) -> np.ndarray:
    """A Calotriton asper belly: dark spots on a pale ground, held over wet rock (RGB)."""
    rng = np.random.default_rng(seed)
    stone = np.random.default_rng(seed if background_seed is None else background_seed)
    image = (
        stone.integers(60, 110, size=(300, 512, 1)).astype(np.uint8).repeat(3, axis=2)
        * np.array([0.95, 0.98, 1.0])
    ).astype(np.uint8)
    body = np.zeros(image.shape[:2], np.uint8)
    cv2.fillPoly(body, [np.array(_BODY, np.int32).reshape(-1, 1, 2)], 255)
    image[body > 0] = (224, 172, 110)  # pale orange ventral ground
    for _ in range(rng.integers(26, 36)):  # the individual's dark ventral spots
        blob = np.zeros(image.shape[:2], np.uint8)
        cv2.ellipse(
            blob,
            (int(rng.integers(90, 430)), int(rng.integers(100, 210))),
            (int(rng.integers(7, 18)), int(rng.integers(5, 13))),
            int(rng.integers(0, 180)),
            0,
            360,
            255,
            -1,
        )
        image[cv2.bitwise_and(blob, body) > 0] = (54, 44, 40)
    return cv2.GaussianBlur(image, (3, 3), 0)


def test_calotriton_band_pass_survives_wet_field_lighting() -> None:
    """A newt is photographed straight out of a stream, so its belly is wet and reflective.

    Its pattern is a *lightness* pattern, so no colour channel can rescue it — but the illumination
    is a low spatial frequency and the spots are not, which is what the band-pass exploits. The old
    global-histogram default is kept as a config option, and must do measurably worse here.
    """
    catalog, queries = _wet_captures(_newt_belly, np.random.default_rng(9))
    roi = _body_roi()
    band = _rank_catalog(CalotritonAsperModule(), roi, catalog, queries)
    equalized = _rank_catalog(
        CalotritonAsperModule(config={"normalization": "equalize"}), roi, catalog, queries
    )
    assert band.hits == band.queries, f"the band-pass missed {band.queries - band.hits}"
    assert band.worst_same > band.best_other, "true matches must outscore false ones"
    # The effect is large. The score saturates near 1 once a match has many agreeing keypoints, so
    # compare how convincingly each recipe separates true from false matches (the gap between the
    # weakest recapture and the strongest impostor), not raw means.
    band_gap = band.worst_same - band.best_other
    assert band_gap > 1.5 * (equalized.worst_same - equalized.best_other)
    assert band.worst_same > equalized.worst_same


def test_calotriton_still_handles_a_clean_capture() -> None:
    """The old default was never wrong for even, standardised photographs — nor is the new one."""
    module = CalotritonAsperModule()
    roi = _body_roi()
    animal = _newt_belly(41)
    query = OrbAlgorithm().extract_features(module.preprocess(_rotate(animal, 9), roi))
    target = OrbAlgorithm().extract_features(module.preprocess(animal, roi))
    other = OrbAlgorithm().extract_features(module.preprocess(_newt_belly(42), roi))
    algorithm = OrbAlgorithm()
    assert algorithm.compare(query, target).normalized_score > 0.5
    assert (
        algorithm.compare(query, target).normalized_score
        > algorithm.compare(query, other).normalized_score
    )


def test_first_party_plugins_discoverable_via_entry_points() -> None:
    registry = PluginRegistry()
    discover_entry_points(registry)
    assert registry.algorithm("orb") is not None
    assert registry.algorithm("sift_lnbnn") is not None
    for module_id in ("calotriton_asper", "salamandra_salamandra"):
        assert registry.module(module_id) is not None
        # capability matching wires each module to both keypoint algorithms
        module = registry.create_module(module_id)
        compatible = {record.descriptor.algorithm_id for record in registry.algorithms_for(module.compatible_algorithms())}
        assert {"orb", "sift_lnbnn"} <= compatible


def test_species_modules_do_not_collide() -> None:
    """Two modules must not claim the same id or the same species."""
    registry = PluginRegistry()
    discover_entry_points(registry)
    records = registry.modules()
    ids = [r.descriptor.module_id for r in records]
    species = [name for r in records for name in r.descriptor.supported_species]
    assert len(ids) == len(set(ids))
    assert len(species) == len(set(species))


# ---------------------------------------------------------------------------------------------
# Salamandra salamandra: a black animal patterned in yellow, photographed in the field.
# ---------------------------------------------------------------------------------------------
_BODY = ((60, 100), (260, 60), (450, 105), (450, 200), (250, 250), (60, 205))


def _fire_salamander(seed: int, background_seed: int | None = None) -> np.ndarray:
    """A black-bodied, yellow-blotched animal on leaf litter (RGB, as the image store loads)."""
    rng = np.random.default_rng(seed)
    litter = np.random.default_rng(seed if background_seed is None else background_seed)
    image = (
        litter.integers(70, 130, size=(300, 512, 1)).astype(np.uint8).repeat(3, axis=2)
        * np.array([1.0, 0.78, 0.5])
    ).astype(np.uint8)
    body = np.zeros(image.shape[:2], np.uint8)
    cv2.fillPoly(body, [np.array(_BODY, np.int32).reshape(-1, 1, 2)], 255)
    image[body > 0] = (28, 24, 22)  # glossy black skin
    for _ in range(rng.integers(14, 20)):  # the individual's unique yellow blotches
        blob = np.zeros(image.shape[:2], np.uint8)
        cv2.ellipse(
            blob,
            (int(rng.integers(90, 430)), int(rng.integers(100, 210))),
            (int(rng.integers(10, 26)), int(rng.integers(7, 18))),
            int(rng.integers(0, 180)),
            0,
            360,
            255,
            -1,
        )
        image[cv2.bitwise_and(blob, body) > 0] = (236, 196, 40)
    return cv2.GaussianBlur(image, (3, 3), 0)


def _field_capture(image: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """The same animal photographed again, at night, by hand: new pose, exposure, colour cast,
    a shadow across the body and specular glare on the wet skin."""
    h, w = image.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), float(rng.uniform(-12, 12)), 1.05)
    out = cv2.warpAffine(image, matrix, (w, h), borderMode=cv2.BORDER_REFLECT).astype(np.float32)

    start = float(rng.uniform(0.35, 0.7))  # torchlight falls off across the frame
    gradient = np.linspace(start, start + 0.8, w, dtype=np.float32)[None, :, None]
    if rng.random() < 0.5:
        gradient = gradient[:, ::-1, :]
    cast = np.array(rng.choice([[1.25, 1.02, 0.72], [0.78, 0.94, 1.28]]), np.float32)
    out = out * gradient * cast * float(rng.uniform(0.75, 1.25))

    shadow = np.ones(out.shape[:2], np.float32)  # a leaf or the observer's hand
    cv2.line(shadow, (int(rng.integers(0, w)), 0), (int(rng.integers(0, w)), h), 0.45, 80)
    out = out * cv2.GaussianBlur(shadow, (0, 0), 11)[..., None]

    for _ in range(4):  # specular highlights on wet skin
        spot = np.zeros(out.shape[:2], np.float32)
        cv2.circle(spot, (int(rng.integers(100, 420)), int(rng.integers(90, 220))), 18, 1.0, -1)
        spot = cv2.GaussianBlur(spot, (0, 0), 8)
        out = out * (1 - spot[..., None]) + 255.0 * spot[..., None]
    return np.clip(out, 0, 255).astype(np.uint8)


def _body_roi() -> api.ROI:
    return api.ROI(kind=api.ROIKind.POLYGON, points=tuple((float(x), float(y)) for x, y in _BODY))


class TestSalamandraConformance(SpeciesModuleContract):
    def make_module(self) -> api.SpeciesModule:
        return SalamandraSalamandraModule()


def test_salamandra_profile() -> None:
    profile = SalamandraSalamandraModule().define_species_profile()
    assert profile.scientific_name == "Salamandra salamandra"
    assert profile.pattern_region == "dorsal"
    assert profile.roi.kind is api.ROIKind.POLYGON
    assert not profile.roi.allow_auto_suggest  # the region is drawn by hand
    assert {f.key for f in profile.measurements} == {
        "svl",
        "total_length",
        "weight",
        "sex",
        "life_stage",
        "pattern_type",
    }
    assert api.AlgorithmFamily.KEYPOINT in profile.compatible_algorithms.families
    assert {s.key for s in profile.derived_statistics} >= {
        "mean_svl",
        "sex_ratio",
        "pattern_types",
        "body_condition",
    }


def test_salamandra_body_condition_statistic() -> None:
    """The declared DERIVED statistic is Fulton's K, and ignores incomplete or absurd records."""
    spec = next(
        s
        for s in SalamandraSalamandraModule().define_species_profile().derived_statistics
        if s.key == "body_condition"
    )
    assert spec.compute is not None
    assert spec.compute({"svl": 100.0, "weight": 40.0}) == pytest.approx(4.0)
    assert spec.compute({"svl": 100.0}) is None  # no weight
    assert spec.compute({"svl": 0.0, "weight": 40.0}) is None  # would divide by zero
    assert spec.compute({"svl": "long", "weight": 40.0}) is None  # not a number


def test_salamandra_preprocess_extracts_the_yellow_pattern() -> None:
    """The pattern map must carry the blotches, not the illumination.

    The test for that is direct: photograph the same animal under two very different lightings and
    the extracted pattern must come out nearly the same.
    """
    module = SalamandraSalamandraModule()
    animal = _fire_salamander(3)
    roi = _body_roi()
    sample = module.preprocess(_field_capture(animal, np.random.default_rng(0)), roi)

    assert sample.is_grayscale
    assert sample.image.dtype == np.uint8
    assert sample.roi_mask is not None
    assert sample.meta["pattern_source"] == "lab_b"  # read chromatically, not from luminance

    warm = np.clip(animal * np.array([1.3, 1.0, 0.7]), 0, 255).astype(np.uint8)
    gradient = np.linspace(0.4, 1.3, animal.shape[1], dtype=np.float32)[None, :, None]
    dim = np.clip(animal * gradient, 0, 255).astype(np.uint8)
    warm_pattern = module.preprocess(warm, roi).image.astype(float)
    dim_pattern = module.preprocess(dim, roi).image.astype(float)
    assert float(np.mean(np.abs(warm_pattern - dim_pattern))) < 12.0, (
        "a colour cast and a light gradient must not change the extracted pattern"
    )


def test_salamandra_preprocess_survives_a_greyscale_capture() -> None:
    """Monochrome material still works — with a warning, since colour is what the module reads."""
    module = SalamandraSalamandraModule()
    grey = cv2.cvtColor(_fire_salamander(4), cv2.COLOR_RGB2GRAY)
    sample = module.preprocess(grey, _body_roi())
    assert sample.is_grayscale
    assert sample.meta["pattern_source"] == "intensity"

    result = module.validate_image(grey)
    assert result.ok  # a warning, not a rejection
    assert [issue.code for issue in result.warnings] == ["monochrome"]
    assert not SalamandraSalamandraModule().validate_image(_fire_salamander(4)).warnings


@dataclass(frozen=True)
class _Ranking:
    """How a preprocessing choice performs over a catalog: hits, and how convincing the evidence is."""

    hits: int
    queries: int
    mean_same: float
    worst_same: float
    best_other: float


def _rank_catalog(module: api.SpeciesModule, roi: api.ROI, catalog, queries) -> _Ranking:
    """Rank every query against the whole catalog with ORB, and summarize."""
    algorithm = OrbAlgorithm()
    features = {
        seed: algorithm.extract_features(module.preprocess(image, roi))
        for seed, image in catalog.items()
    }
    same, other, hits = [], [], 0
    for seed, image in queries.items():
        query = algorithm.extract_features(module.preprocess(image, roi))
        scored = {
            target: algorithm.compare(query, features[target]).normalized_score for target in features
        }
        same.append(scored[seed])
        other.extend(score for target, score in scored.items() if target != seed)
        hits += int(max(scored, key=lambda key: scored[key]) == seed)
    return _Ranking(hits, len(queries), float(np.mean(same)), float(np.min(same)), float(np.max(other)))


_WET_SEEDS = tuple(range(30, 36))


def _wet_captures(make, rng, seeds=_WET_SEEDS):
    """A catalog and a query set of the same animals, photographed on different substrates."""
    catalog = {seed: _field_capture(make(seed, 500 + seed), rng) for seed in seeds}
    queries = {seed: _field_capture(make(seed, 900 + seed), rng) for seed in seeds}
    return catalog, queries


def test_salamandra_yellowness_channel_earns_its_place() -> None:
    """The species-specific decision this module makes, measured rather than asserted.

    Same captures, same band-pass, same algorithm — only the *channel* differs. The margin is real
    but **modest**: once the band-pass has removed the illumination, band-passed luminance also ranks
    these captures correctly. Yellow on black is simply a higher-contrast signal in ``b*`` than in
    grey, which yields more repeatable keypoints — this is not an illumination-invariance argument,
    and measuring one nuisance at a time shows ``b*`` is in fact *more* sensitive to colour casts.
    """
    catalog, queries = _wet_captures(_fire_salamander, np.random.default_rng(5))
    roi = _body_roi()
    chromatic = _rank_catalog(SalamandraSalamandraModule(), roi, catalog, queries)
    achromatic = _rank_catalog(
        SalamandraSalamandraModule(config={"channel": "luminance"}), roi, catalog, queries
    )
    assert chromatic.hits == chromatic.queries
    assert chromatic.worst_same > chromatic.best_other, "true matches must outscore false ones"
    assert chromatic.mean_same > achromatic.mean_same, (
        "if luminance matched it here, the chromatic default would be unjustified"
    )


def test_salamandra_roi_margin_keeps_edge_keypoints() -> None:
    """Cropping flush to the ROI feeds the pattern's edge into ORB's blind border; the margin
    (``roi_margin``) is what keeps those keypoints, so it must widen the sample."""
    capture = _field_capture(_fire_salamander(9), np.random.default_rng(2))
    roi = _body_roi()
    flush = SalamandraSalamandraModule(config={"roi_margin": 0}).preprocess(capture, roi)
    padded = SalamandraSalamandraModule().preprocess(capture, roi)
    assert padded.image.shape[0] > flush.image.shape[0]
    assert padded.image.shape[1] > flush.image.shape[1]
    assert padded.roi_mask is not None and padded.roi_mask.shape[:2] == padded.image.shape[:2]

    algorithm = OrbAlgorithm()
    assert (
        algorithm.extract_features(padded).descriptors.shape[0]
        > algorithm.extract_features(flush).descriptors.shape[0]
    )
