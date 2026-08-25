"""Pixel → real-world scale (spec 5.5). Pure function; every path records its assumption.

Priority (most → least reliable):
  1. user-entered facade width/height
  2. detected main door height  (standard 7 ft)
  3. median window height       (standard 4 ft)
  4. floor count × 10 ft storey height
  5. default facade width 30 ft
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from statistics import median

DOOR_FT = 7.0
WINDOW_FT = 4.0
STOREY_FT = 10.0
DEFAULT_FACADE_FT = 30.0


@dataclass
class ScaleResult:
    ft_per_px: float
    method: str
    confidence: str  # high | medium | low
    assumptions: list[str] = field(default_factory=list)


def _silhouette(regions: list[dict]) -> tuple[float, float] | None:
    walls = [r for r in regions if r["label"] in ("wall", "parapet")]
    if not walls:
        return None
    x0 = min(r["bbox"][0] for r in walls)
    x1 = max(r["bbox"][0] + r["bbox"][2] for r in walls)
    y0 = min(r["bbox"][1] for r in walls)
    y1 = max(r["bbox"][1] + r["bbox"][3] for r in walls)
    return float(x1 - x0), float(y1 - y0)


def estimate(
    regions: list[dict],
    image_w: int,
    facade_width_ft: float | None = None,
    facade_height_ft: float | None = None,
    floors: int | None = None,
) -> ScaleResult:
    sil = _silhouette(regions)
    # Degenerate (zero-extent) silhouettes fall back to the image width so nothing divides by 0.
    sil_w = sil[0] if sil and sil[0] >= 1 else float(max(image_w, 1))
    sil_h = sil[1] if sil and sil[1] >= 1 else None

    if facade_width_ft or (facade_height_ft and sil_h):
        factors, notes = [], []
        if facade_width_ft:
            factors.append(facade_width_ft / sil_w)
            notes.append(f"facade width entered by user = {facade_width_ft:g} ft")
        if facade_height_ft and sil_h:
            factors.append(facade_height_ft / sil_h)
            notes.append(f"facade height entered by user = {facade_height_ft:g} ft")
        # Areas scale with ft_per_px²: the geometric mean of the two factors preserves the
        # user's width × height product exactly, unlike the arithmetic mean.
        ft_per_px = math.prod(factors) ** (1.0 / len(factors))
        return ScaleResult(ft_per_px, "user_measurement", "high", notes)

    doors = [
        r
        for r in regions
        if r["label"] == "door"
        and r["bbox"][3] > 0
        and 1.3 <= r["bbox"][3] / max(r["bbox"][2], 1) <= 4.5
    ]
    if doors:
        d = max(doors, key=lambda r: r["bbox"][3])
        return ScaleResult(
            DOOR_FT / d["bbox"][3],
            "door_reference",
            "medium",
            [f"main door ({d['name']}) assumed {DOOR_FT:g} ft tall"],
        )

    windows = [r for r in regions if r["label"] == "window" and r["bbox"][3] > 0]
    if len(windows) >= 2:
        h = median(r["bbox"][3] for r in windows)
        return ScaleResult(
            WINDOW_FT / h,
            "window_reference",
            "medium",
            [f"median window height ({len(windows)} windows) assumed {WINDOW_FT:g} ft"],
        )

    if floors and sil_h:
        return ScaleResult(
            floors * STOREY_FT / sil_h,
            "floor_count",
            "low",
            [f"{floors} floors × {STOREY_FT:g} ft per floor"],
        )

    return ScaleResult(
        DEFAULT_FACADE_FT / sil_w,
        "default_assumption",
        "low",
        [f"no reference found; facade width assumed {DEFAULT_FACADE_FT:g} ft"],
    )
