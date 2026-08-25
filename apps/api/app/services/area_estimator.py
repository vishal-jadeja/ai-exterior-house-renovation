"""Surface areas and lengths per region (spec 5.5). Pure numpy/OpenCV.

wall/parapet/pillar : net area = polygon area − openings inside it (windows, doors, railings…)
railing/roof_edge   : running length = bbox width
gate                : area (bbox) + length
pillar              : visible height × estimated perimeter (assumes ~1 ft depth)
A mild foreshortening factor compensates for surfaces seen at an angle.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
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
    """Ratio of left/right (or top/bottom) edge lengths of the bounding quad → >1 when skewed."""
    if len(poly) < 4:
        return 1.0
    rect = cv2.minAreaRect(poly.astype(np.float32))
    (w, h), angle = rect[1], rect[2]
    if w == 0 or h == 0:
        return 1.0
    # A polygon whose min-area rect is rotated much from axis-aligned is likely viewed obliquely.
    tilt = min(abs(angle) % 90, 90 - abs(angle) % 90) / 45.0  # 0 (aligned) … 1 (45°)
    return float(min(MAX_FORESHORTEN, 1.0 + 0.4 * tilt))


def measure(
    regions: list[dict], ft_per_px: float, image_w: int, image_h: int
) -> list[SurfaceMeasure]:
    h, w = image_h, image_w
    openings = np.zeros((h, w), np.uint8)
    for r in regions:
        if r["label"] in OPENING_LABELS:
            openings |= rasterize(r["polygon"], h, w)

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
            area = h_ft * (2 * (w_ft + PILLAR_DEPTH_FT)) * 0.75  # 3 faces visible/paintable
            method = "height × perimeter (depth assumed 1 ft)"
            notes.append("pillar depth assumed 1 ft; 3 of 4 faces counted")
        elif label in ("railing", "roof_edge"):
            net = gross
            length = r["bbox"][2] * ft_per_px * fs
            area = gross * ft_per_px**2
            method = "bbox width × scale (running length)"
        elif label == "gate":
            net = gross
            length = r["bbox"][2] * ft_per_px
            area = r["bbox"][2] * r["bbox"][3] * ft_per_px**2
            method = "bbox area × scale²"
        else:  # window, door, balcony — informational only
            net = gross
            area = gross * ft_per_px**2 * fs
        if fs > 1.02:
            notes.append(f"foreshortening ×{fs:.2f} applied (surface viewed at an angle)")
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
