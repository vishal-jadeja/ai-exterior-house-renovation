"""Surface areas and lengths per region (spec 5.5). Pure numpy/OpenCV.

wall/parapet        : net area = polygon area − openings inside it (windows, doors, railings…)
railing/roof_edge/
balcony             : running length along the strip + visible face area
gate                : area (bbox) + length
pillar              : visible height × (width + 2 × assumed 1 ft depth) — 3 faces
A conservative foreshortening factor compensates for surfaces seen at an angle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from app.services.region_mapper import rasterize
from app.services.taxonomy import OPENING_LABELS

PILLAR_DEPTH_FT = 1.0
MAX_FORESHORTEN = 1.4


@dataclass
class SurfaceMeasure:
    region_id: str
    label: str
    name: str
    gross_px: float
    net_px: float
    area_sqft: float
    length_ft: float | None
    foreshortening: float
    method: str
    confidence: float
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def _foreshortening(poly: np.ndarray) -> float:
    """Perspective correction for a surface photographed at an angle.

    A rectangular wall seen obliquely projects to a trapezoid: its near vertical edge is taller
    than its far one (or, for a surface above/below the camera, the near horizontal edge is
    longer). We compare the vertical extent of the polygon's left-most and right-most bands and
    the horizontal extent of its top/bottom bands; the larger of the two ratios drives a
    conservative correction (half of the excess, capped) so a 45° view (~×1.41 true) gets ~×1.25.
    Axis-aligned rectangles and near-symmetric blobs get exactly 1.0.
    """
    if len(poly) < 4:
        return 1.0
    xs, ys = poly[:, 0], poly[:, 1]
    w, h = float(xs.max() - xs.min()), float(ys.max() - ys.min())
    if w < 4 or h < 4:
        return 1.0

    def _extent(mask: np.ndarray, values: np.ndarray) -> float:
        sel = values[mask]
        return float(sel.max() - sel.min()) if len(sel) >= 2 else 0.0

    band = 0.2
    left = _extent(xs <= xs.min() + band * w, ys)
    right = _extent(xs >= xs.max() - band * w, ys)
    top = _extent(ys <= ys.min() + band * h, xs)
    bottom = _extent(ys >= ys.max() - band * h, xs)

    def _ratio(a: float, b: float) -> float:
        lo, hi = min(a, b), max(a, b)
        # Both bands must hold a real edge; otherwise the polygon is not quad-like here.
        if lo < 0.25 * (h if a is left or a is right else w):
            return 1.0
        return hi / lo

    ratio = max(_ratio(left, right), _ratio(top, bottom))
    return float(min(MAX_FORESHORTEN, 1.0 + 0.5 * (ratio - 1.0)))


def _polyline_length(poly: np.ndarray) -> float:
    """Running length of a thin, possibly sloped strip (railing, roof edge, balcony front).

    Takes the *shorter* of the two vertex chains between the polygon's left-most and right-most
    points: for a strip both chains run along it, and the longer one also includes the end caps.
    A horizontal 300×30 rectangle gives exactly 300; a parallelogram gives its slanted edge.
    """
    if len(poly) < 2:
        return 0.0
    i0, i1 = int(np.argmin(poly[:, 0])), int(np.argmax(poly[:, 0]))
    if i0 == i1:
        return 0.0
    n = len(poly)
    idx = [(i0 + k) % n for k in range((i1 - i0) % n + 1)]
    chain_a = float(np.sum(np.linalg.norm(np.diff(poly[idx], axis=0), axis=1)))
    idx = [(i1 + k) % n for k in range((i0 - i1) % n + 1)]
    chain_b = float(np.sum(np.linalg.norm(np.diff(poly[idx], axis=0), axis=1)))
    return min(chain_a, chain_b)


def measure(
    regions: list[dict], ft_per_px: float, image_w: int, image_h: int
) -> list[SurfaceMeasure]:
    h, w = image_h, image_w
    openings = np.zeros((h, w), np.uint8)
    railings = np.zeros((h, w), np.uint8)
    for r in regions:
        if r["label"] in OPENING_LABELS:
            openings |= rasterize(r["polygon"], h, w)
        if r["label"] == "railing":
            railings |= rasterize(r["polygon"], h, w)

    out: list[SurfaceMeasure] = []
    for r in regions:
        poly = np.array(r["polygon"], np.float32)
        mask = rasterize(r["polygon"], h, w)
        gross = float(mask.sum())
        label = r["label"]
        notes: list[str] = []
        fs = _foreshortening(poly)
        length = None
        method = "pixel_area × scale²"
        if label in ("wall", "parapet"):
            net = float((mask & ~openings).sum())
            if gross and net < gross:
                notes.append(f"openings subtracted: {100 * (1 - net / gross):.0f}% of gross")
            area = net * ft_per_px**2 * fs
            if label == "parapet":
                length = r["bbox"][2] * ft_per_px
        elif label == "pillar":
            net = float((mask & ~openings).sum())
            h_ft = r["bbox"][3] * ft_per_px
            w_ft = max(r["bbox"][2] * ft_per_px, 0.5)
            # Front face (w) plus the two visible sides (assumed depth each): 3 of 4 faces.
            area = h_ft * (w_ft + 2 * PILLAR_DEPTH_FT)
            method = "height × (width + 2 × depth)"
            notes.append(f"pillar depth assumed {PILLAR_DEPTH_FT:g} ft; 3 of 4 faces counted")
        elif label in ("railing", "roof_edge", "balcony"):
            # Running length along the strip (follows slope for stair/ramp railings) …
            net = gross
            if label == "balcony":
                # A railing drawn on top of the balcony is priced as its own region.
                net = float((mask & ~railings).sum())
                if gross and net < gross:
                    notes.append(f"railing excluded: {100 * (1 - net / gross):.0f}% of gross")
            length = max(_polyline_length(poly), float(r["bbox"][2])) * ft_per_px
            # … and the visible front face, for materials priced per area.
            area = net * ft_per_px**2 * fs
            method = "polyline length × scale (running length); face area = pixel area × scale²"
        elif label == "gate":
            net = gross
            length = r["bbox"][2] * ft_per_px
            area = r["bbox"][2] * r["bbox"][3] * ft_per_px**2
            method = "bbox area × scale²"
        else:  # window, door — informational only
            net = gross
            area = gross * ft_per_px**2 * fs
        fs_applied = label not in ("pillar", "gate")  # those use bbox-based formulas
        if fs > 1.02 and fs_applied:
            notes.append(f"foreshortening ×{fs:.2f} applied (surface viewed at an angle)")
        if not fs_applied:
            fs = 1.0
        conf = float(r.get("confidence", 0.6))
        out.append(
            SurfaceMeasure(
                region_id=r["id"],
                label=label,
                name=r["name"],
                gross_px=gross,
                net_px=net,
                area_sqft=round(area, 1),
                length_ft=round(length, 1) if length else None,
                foreshortening=round(fs, 3),
                method=method,
                confidence=round(conf, 2),
                notes=notes,
            )
        )
    return out
