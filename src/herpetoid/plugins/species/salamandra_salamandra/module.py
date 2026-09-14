"""Species module for *Salamandra salamandra* (fire salamander).

Identification uses the individual's unique **dorsal** pattern of yellow spots, blotches or stripes on
a glossy black ground. The user marks the dorsum (a polygon ROI); preprocessing turns it into a
:class:`~herpetoid.api.Sample` that keypoint algorithms (ORB) can match.

Preprocessing does two separable things, and it is worth being precise about which one earns what.

**Removing the illumination — the part that matters most.** A fire salamander is photographed at
night with a torch or a flash: exposure, colour cast and hard shadows vary hugely between captures.
They vary *slowly across the frame*, though, while the pattern does not, so a **band-pass** separates
them. Its widths are fractions of the marked region rather than pixel counts, so the filter tracks
the animal's size in the frame instead of the photographer's distance. This single change is what
takes the module from unreliable to dependable, and the brook newt module does exactly the same
thing — see :mod:`herpetoid.plugins.species.calotriton_asper`.

**Choosing the channel — a smaller, species-specific gain.** Yellow on black is a higher-contrast
signal on the b\\* (blue→yellow) axis of CIE Lab than in grey, which yields more repeatable
keypoints, so ``b*`` is the default. Be careful with the reason: this is *not* an
illumination-invariance argument. Measuring one nuisance at a time shows ``b*`` is actually **more**
sensitive to an exposure change or a colour cast than band-passed luminance is (a warm cast moves
the yellow axis by definition), and specular glare corrupts either channel depending on whether it
lands on a blotch or on skin. The honest claim is the ranking margin below — and ``channel`` is a
config option precisely so the choice can be re-measured rather than believed.

Ranking the true recapture first against the whole catalog, on synthetic captures of individuals
photographed twice on different substrates, each with its own pose, illumination gradient, colour
cast, shadow, wet-skin glare and sensor noise:

=========================================  ==================  ==========================
pattern extraction                         correct match 1st   worst same / best different
=========================================  ==================  ==========================
greyscale + histogram equalization          22 / 40            0.000 / 0.471
yellowness, stretched + Otsu (v1.0)         40 / 40            0.360 / 0.465  (overlap)
band-passed luminance                       39 / 40            0.397 / 0.467
**yellowness + band-pass (this, v1.1)**     **30 / 30**        **0.787 / 0.356**
=========================================  ==================  ==========================

Read the last two rows together: most of the distance from the first row is the band-pass, not the
channel. The v1.0 recipe ranked correctly but its score ranges *overlapped* — some true recaptures
scored below the best false match, which a reviewer reads as an unconvincing shortlist. Binarizing
with Otsu after a band-pass measured worse for both species and was dropped.

The scores in this table and the next were measured with ORB 1.0, which averaged the inlier count
with the inlier ratio. ORB 1.1 scores by agreeing matches alone (see
:mod:`herpetoid.plugins.algorithms.orb.algorithm`), so compare the rows with each other, not with
today's numbers.

**Those figures come from synthetic images** (the generators live in ``tests/test_plugins.py``).
On the two real field photographs available so far — different animals, hand-drawn ROIs, matched
against re-posed copies of themselves — the ranking held up but the *channel* comparison came out the
other way round:

=========================  ===========================  ==========================
channel (real photographs)  same animal, re-posed        different animals
=========================  ===========================  ==========================
yellowness (default)        0.953                        0.263
luminance                   0.988                        0.000
=========================  ===========================  ==========================

Two animals and a single false pair is far too little to overturn a default on, so ``yellowness``
stands — but it is not the settled question the synthetic study made it look like, and it is the
first thing to re-measure when a real catalogue exists. Flip ``channel`` to ``"luminance"`` to try it.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from herpetoid.api import (
    ROI,
    AlgorithmCompatibility,
    AlgorithmFamily,
    DerivedStatistic,
    ExportFormatSpec,
    FieldDefinition,
    FieldGroup,
    FieldType,
    ModuleContext,
    ModuleDescriptor,
    ROIKind,
    ROISpec,
    Sample,
    Severity,
    SpeciesModule,
    SpeciesProfile,
    StatisticKind,
    Validation,
    ValidationIssue,
    ValidationResult,
)
from herpetoid.api.preprocessing import (
    DEFAULT_ROI_MARGIN,
    band_pass,
    crop_to_roi,
    is_color,
    luminance,
    yellowness,
)

_DEFAULT_CONFIG: dict[str, Any] = {
    # Which channel carries the pattern. 'yellowness' is the point of this module; 'luminance' is
    # offered so the choice can be measured rather than asserted (see the table above).
    "channel": "yellowness",
    # Band-pass widths, as fractions of the marked region's shorter side: just under the finest
    # blotch edge, and just above the coarsest blotch, so the light field is subtracted away.
    "band_low": 0.006,
    "band_high": 0.040,
    # Keypoint detectors ignore a border, so the crop keeps context around the ROI.
    "roi_margin": DEFAULT_ROI_MARGIN,
}


def _body_condition(measurements: Mapping[str, Any]) -> float | None:
    """Fulton's condition factor ``K = 10⁵ · weight(g) / SVL(mm)³`` (the classic ``100·W/L³``)."""
    svl, weight = measurements.get("svl"), measurements.get("weight")
    if isinstance(svl, bool) or isinstance(weight, bool):
        return None
    if not isinstance(svl, (int, float)) or not isinstance(weight, (int, float)) or svl <= 0:
        return None
    return float(weight) * 1e5 / float(svl) ** 3


class SalamandraSalamandraModule(SpeciesModule):
    """Dorsal yellow-on-black pattern module for *Salamandra salamandra*."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self._config: dict[str, Any] = {**_DEFAULT_CONFIG, **(config or {})}

    @classmethod
    def descriptor(cls) -> ModuleDescriptor:
        return ModuleDescriptor(
            module_id="salamandra_salamandra",
            name="Salamandra salamandra (fire salamander)",
            version="1.1",
            supported_species=("Salamandra salamandra",),
            description="Dorsal yellow-on-black pattern identification for the fire salamander.",
        )

    def initialize(self, ctx: ModuleContext) -> None:
        self._config = {**self._config, **dict(ctx.config)}

    def define_species_profile(self) -> SpeciesProfile:
        measurements = (
            FieldDefinition(
                "svl",
                "SVL",
                FieldType.FLOAT,
                group=FieldGroup.MEASUREMENT,
                unit="mm",
                validation=Validation(min_value=0.0),
                help_text="Snout-vent length, snout tip to the posterior edge of the vent.",
                include_in_statistics=True,
                order=1,
            ),
            FieldDefinition(
                "total_length",
                "Total length",
                FieldType.FLOAT,
                group=FieldGroup.MEASUREMENT,
                unit="mm",
                validation=Validation(min_value=0.0),
                help_text="Snout tip to tail tip. Record it as unreliable if the tail is regrown.",
                include_in_statistics=True,
                order=2,
            ),
            FieldDefinition(
                "weight",
                "Weight",
                FieldType.FLOAT,
                group=FieldGroup.MEASUREMENT,
                unit="g",
                validation=Validation(min_value=0.0),
                include_in_statistics=True,
                order=3,
            ),
            FieldDefinition(
                "sex",
                "Sex",
                FieldType.CHOICE,
                group=FieldGroup.GENERAL,
                choices=("male", "female", "undetermined"),
                include_in_statistics=True,
                order=4,
            ),
            FieldDefinition(
                "life_stage",
                "Life stage",
                FieldType.CHOICE,
                group=FieldGroup.GENERAL,
                choices=("larva", "juvenile", "subadult", "adult"),
                include_in_statistics=True,
                order=5,
            ),
            FieldDefinition(
                "pattern_type",
                "Dorsal pattern",
                FieldType.CHOICE,
                group=FieldGroup.GENERAL,
                choices=("spotted", "striped", "mixed"),
                help_text="Arrangement of the yellow: irregular spots, longitudinal stripes, or both.",
                include_in_statistics=True,
                order=6,
            ),
        )
        derived_statistics = (
            DerivedStatistic(
                "mean_svl", "Mean SVL", StatisticKind.AGGREGATE, source_field="svl", unit="mm"
            ),
            DerivedStatistic(
                "mean_weight",
                "Mean weight",
                StatisticKind.AGGREGATE,
                source_field="weight",
                unit="g",
            ),
            DerivedStatistic(
                "sex_ratio", "Sex ratio", StatisticKind.DISTRIBUTION, source_field="sex"
            ),
            DerivedStatistic(
                "pattern_types",
                "Dorsal pattern types",
                StatisticKind.DISTRIBUTION,
                source_field="pattern_type",
            ),
            DerivedStatistic(
                "svl_growth",
                "Growth (SVL over time)",
                StatisticKind.GROWTH,
                source_field="svl",
                unit="mm",
            ),
            DerivedStatistic(
                "body_condition",
                "Mean body condition (Fulton's K)",
                StatisticKind.DERIVED,
                compute=_body_condition,
            ),
        )
        return SpeciesProfile(
            scientific_name="Salamandra salamandra",
            common_name="Fire salamander",
            taxonomy={
                "class": "Amphibia",
                "order": "Urodela",
                "family": "Salamandridae",
                "genus": "Salamandra",
            },
            description=(
                "A stout, nocturnal salamander of humid broadleaf forest and their streams, "
                "widespread across western, central and southern Europe."
            ),
            identification_notes=(
                "Each individual carries a unique arrangement of yellow spots, blotches or stripes "
                "on a glossy black ground. The dorsal pattern is set at metamorphosis and stable "
                "for life, so it works as a natural tag. Photograph the animal from directly above, "
                "in even light, with the head and the whole trunk in frame — and in colour, which is "
                "what this module reads the pattern from."
            ),
            pattern_region="dorsal",
            roi=ROISpec(
                kind=ROIKind.POLYGON,
                interactive=True,
                guidance="Draw a polygon around the dorsal pattern, from the head to the tail base.",
            ),
            compatible_algorithms=AlgorithmCompatibility(
                families=(AlgorithmFamily.KEYPOINT,), requires_grayscale=True, requires_mask=True
            ),
            measurements=measurements,
            derived_statistics=derived_statistics,
            export_formats=(
                ExportFormatSpec("csv"),
                ExportFormatSpec("xlsx"),
                ExportFormatSpec("json"),
                ExportFormatSpec("pdf"),
            ),
        )

    def preprocess(self, image: np.ndarray, roi: ROI) -> Sample:
        config = self._config
        region, region_mask = crop_to_roi(np.asarray(image), roi, int(config["roi_margin"]))

        chromatic = str(config["channel"]) == "yellowness" and is_color(region)
        values = yellowness(region) if chromatic else luminance(region)
        pattern = band_pass(
            values,
            region_mask,
            low_fraction=float(config["band_low"]),
            high_fraction=float(config["band_high"]),
        )
        # Outside the ROI is left as it is rather than blanked: the mask already confines *detection*
        # to the pattern, and a hard mask edge would cut whichever blotches the user's polygon
        # happens to clip — which differs between two captures of the same animal.
        return Sample(
            image=np.ascontiguousarray(pattern),
            roi_mask=region_mask,
            color_space="gray",
            meta={
                "species": "Salamandra salamandra",
                "pattern_source": "lab_b" if chromatic else "intensity",
            },
        )

    def validate_image(
        self, image: np.ndarray, ctx: ModuleContext | None = None
    ) -> ValidationResult:
        """The base checks, plus a warning when the capture carries no colour to read."""
        result = super().validate_image(image, ctx)
        if result.ok and not is_color(np.asarray(image)):
            return result.merge(
                ValidationResult.of(
                    [
                        ValidationIssue(
                            "monochrome",
                            "This is a greyscale image. The fire salamander pattern is read from "
                            "colour; matching a monochrome capture is less reliable.",
                            Severity.WARNING,
                        )
                    ]
                )
            )
        return result
