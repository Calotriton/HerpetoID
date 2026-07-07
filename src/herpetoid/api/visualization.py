"""Qt-free visualization primitives.

Plugins return *overlay data* (points, lines, polygons, masks, heatmaps) rather than GUI widgets; the
Core presentation layer renders these on its image views. This keeps the SDK independent of PySide6.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from .enums import OverlayKind

Color = tuple[int, int, int, int]  # RGBA, 0-255


@dataclass(slots=True)
class Overlay:
    """A single visualization primitive to draw over an image."""

    kind: OverlayKind
    points: np.ndarray | None = None  # (N, 2); for RECTANGLE two opposite corners
    mask: np.ndarray | None = None  # for MASK / HEATMAP
    text: str | None = None  # for TEXT
    color: Color = (255, 64, 64, 255)
    width: float = 1.5
    label: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def rectangle(
        cls, x: float, y: float, w: float, h: float, *, color: Color = (255, 64, 64, 255)
    ) -> Overlay:
        return cls(
            OverlayKind.RECTANGLE, points=np.array([[x, y], [x + w, y + h]], float), color=color
        )

    @classmethod
    def points_layer(
        cls, points: Any, *, color: Color = (64, 200, 64, 255), width: float = 3.0
    ) -> Overlay:
        return cls(
            OverlayKind.POINTS, points=np.asarray(points, dtype=float), color=color, width=width
        )

    @classmethod
    def polygon(cls, points: Any, *, color: Color = (64, 160, 255, 255)) -> Overlay:
        return cls(OverlayKind.POLYGON, points=np.asarray(points, dtype=float), color=color)


@dataclass(slots=True)
class Visualization:
    """An ordered set of overlay layers.

    ``target`` selects which panel a pairwise (side-by-side) visualization applies to:
    ``'query'``, ``'target'`` or ``'both'``.
    """

    overlays: tuple[Overlay, ...] = ()
    target: str = "query"

    @classmethod
    def empty(cls) -> Visualization:
        return cls(())
