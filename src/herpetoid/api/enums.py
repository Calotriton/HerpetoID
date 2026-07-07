"""Enumerations shared across the plugin SDK.

All members are ``StrEnum`` so they serialize to stable, human-readable strings (used in the database,
JSON exports, and self-describing project bundles).
"""

from __future__ import annotations

from enum import StrEnum


class FieldType(StrEnum):
    """The data type of a declared observation field."""

    TEXT = "text"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    CHOICE = "choice"
    MULTI_CHOICE = "multi_choice"


class FieldGroup(StrEnum):
    """Logical grouping used to lay out forms and to bucket statistics."""

    GENERAL = "general"
    MEASUREMENT = "measurement"
    ENVIRONMENT = "environment"


class ROIKind(StrEnum):
    """The geometric kind of a region of interest."""

    RECTANGLE = "rectangle"
    POLYGON = "polygon"
    ELLIPSE = "ellipse"
    MASK = "mask"
    LANDMARKS = "landmarks"
    FULL_IMAGE = "full_image"


class Severity(StrEnum):
    """Severity of a validation issue."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class AlgorithmFamily(StrEnum):
    """Broad family an identification algorithm belongs to.

    A species module declares the families it is compatible with (its preprocessed :class:`Sample`
    suits), rather than naming concrete algorithm ids.
    """

    KEYPOINT = "keypoint"  # local features + descriptors (ORB, SIFT, SuperPoint, ...)
    EMBEDDING = "embedding"  # global/region embedding vectors (CNN, DINOv2, ...)
    HYBRID = "hybrid"


class ScoreSemantics(StrEnum):
    """How to interpret an algorithm's raw comparison score."""

    SIMILARITY = "similarity"  # higher = more similar
    DISTANCE = "distance"  # lower = more similar


class Aggregation(StrEnum):
    """Aggregation applied to a numeric field for statistics."""

    MEAN = "mean"
    MEDIAN = "median"
    MIN = "min"
    MAX = "max"
    SUM = "sum"
    STD = "std"
    COUNT = "count"


class StatisticKind(StrEnum):
    """The kind of a declared derived statistic."""

    AGGREGATE = "aggregate"  # numeric field -> single value (e.g. mean SVL)
    DISTRIBUTION = "distribution"  # categorical field -> counts / ratio (e.g. sex ratio)
    GROWTH = "growth"  # numeric field over time, per individual
    DERIVED = "derived"  # custom metric computed by a module-provided pure callable


class OverlayKind(StrEnum):
    """The kind of a visualization overlay primitive (rendered by Core, Qt-free here)."""

    POINTS = "points"
    LINES = "lines"
    POLYGON = "polygon"
    RECTANGLE = "rectangle"
    MASK = "mask"
    HEATMAP = "heatmap"
    TEXT = "text"
