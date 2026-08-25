"""Turn a per-pixel label map into editable, labelled polygon regions.

Pure numpy/OpenCV; independent of the model so it can be unit-tested on synthetic masks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

from app.services.taxonomy import HUMAN, LABELS

MIN_AREA_FRAC = {  # component must cover at least this fraction of the image to survive
    "wall": 0.004,
    "window": 0.0006,
    "door": 0.001,
    "railing": 0.0008,
    "pillar": 0.0006,
    "gate": 0.002,
    "roof_edge": 0.001,
    "balcony": 0.001,
    "parapet": 0.002,
}


@dataclass
class RegionCandidate:
    label: str
    polygon: list[list[int]]
    pixel_area: float
    bbox: list[int]  # x, y, w, h
    confidence: float
    name: str = ""
    source: str = "model"
    meta: dict = field(default_factory=dict)


def polygon_area(poly: list[list[float]]) -> float:
    """Shoelace formula."""
    if len(poly) < 3:
        return 0.0
    x = np.array([p[0] for p in poly], dtype=float)
    y = np.array([p[1] for p in poly], dtype=float)
    return float(abs(np.dot(x, np.roll(y, 1)) - np.dot(y, np.roll(x, 1))) / 2.0)


def rasterize(poly: list[list[float]], h: int, w: int) -> np.ndarray:
    mask = np.zeros((h, w), np.uint8)
    if len(poly) >= 3:
        pts = np.array(poly, dtype=np.int32).reshape(-1, 1, 2)
        cv2.fillPoly(mask, [pts], 1)
    return mask


def _clean(mask: np.ndarray, k: int) -> np.ndarray:
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    m = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    return cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel)


def _components(mask: np.ndarray, label: str, min_area: float, conf_map: np.ndarray | None):
    n, cc, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    out = []
    for i in range(1, n):
        area = float(stats[i, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        comp = (cc == i).astype(np.uint8)
        contours, _ = cv2.findContours(comp, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        cnt = max(contours, key=cv2.contourArea)
        eps = 0.006 * cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, eps, True).reshape(-1, 2)
        if len(approx) < 3:
            continue
        x, y, w, h = (int(v) for v in stats[i, :4])
        conf = float(conf_map[comp.astype(bool)].mean()) if conf_map is not None else 0.6
        out.append(
            RegionCandidate(
                label=label,
                polygon=approx.astype(int).tolist(),
                pixel_area=area,
                bbox=[x, y, w, h],
                confidence=round(conf, 3),
            )
        )
    return out


def extract_regions(
    label_map: np.ndarray, confidence: np.ndarray | None = None, max_per_label: int = 12
) -> list[RegionCandidate]:
    """label_map: HxW array of taxonomy label strings' indices (see LABELS) or -1 for background."""
    h, w = label_map.shape
    total = float(h * w)
    k = max(3, int(round(min(h, w) / 200)) | 1)
    regions: list[RegionCandidate] = []
    for idx, label in enumerate(LABELS):
        if label == "balcony":
            continue  # user-assigned only; the model predicts railings
        mask = (label_map == idx).astype(np.uint8)
        if not mask.any():
            continue
        mask = _clean(mask, k if label != "railing" else 3)
        comps = _components(mask, label, MIN_AREA_FRAC[label] * total, confidence)
        comps.sort(key=lambda r: -r.pixel_area)
        regions.extend(comps[:max_per_label])

    regions = _derive_parapet(regions, h)
    regions = _derive_roof_edge(regions, label_map, h, w)
    _name(regions)
    return regions


def _derive_parapet(regions: list[RegionCandidate], h: int) -> list[RegionCandidate]:
    """Wall components sitting entirely above the highest opening are most likely parapet."""
    openings = [r for r in regions if r.label in ("window", "door", "railing")]
    if not openings:
        return regions
    top_opening_y = min(r.bbox[1] for r in openings)
    for r in regions:
        if r.label == "parapet" and r.bbox[1] > h * 0.35:
            r.label = "wall"  # a cornice/molding band low on the facade is not a parapet
            r.meta["derived"] = "cornice band reclassified as wall"
        if r.label == "wall" and r.bbox[1] + r.bbox[3] <= top_opening_y and r.bbox[1] < h * 0.25:
            r.label = "parapet"
            r.confidence = round(min(r.confidence, 0.45), 3)
            r.meta["derived"] = "wall band above the topmost opening"
    return regions


def _derive_roof_edge(regions, label_map, h, w):
    """Roof edge = top boundary of the building silhouette (walls + parapets), as a thin band."""
    walls = [r for r in regions if r.label in ("wall", "parapet")]
    if not walls:
        return regions
    sil = np.zeros((h, w), np.uint8)
    for r in walls:
        sil |= rasterize(r.polygon, h, w)
    cols = np.where(sil.any(axis=0))[0]
    if cols.size < w * 0.1:
        return regions
    tops = np.array([np.argmax(sil[:, c]) for c in cols])
    band = max(4, h // 60)
    # Sample the edge into a polyline and thicken it into a band polygon.
    step = max(1, cols.size // 40)
    pts = [(int(cols[i]), int(tops[i])) for i in range(0, cols.size, step)]
    if len(pts) < 2:
        return regions
    poly = [[x, max(0, y - band // 2)] for x, y in pts] + [
        [x, y + band // 2] for x, y in reversed(pts)
    ]
    length = float(np.sum(np.hypot(np.diff([p[0] for p in pts]), np.diff([p[1] for p in pts]))))
    regions.append(
        RegionCandidate(
            label="roof_edge",
            polygon=poly,
            pixel_area=float(length * band),
            bbox=[
                int(cols[0]),
                int(tops.min()),
                int(cols[-1] - cols[0]),
                int(tops.max() - tops.min() + band),
            ],
            confidence=0.4,
            meta={"derived": "top boundary of building silhouette", "length_px": round(length, 1)},
        )
    )
    return regions


def _name(regions: list[RegionCandidate]) -> None:
    counters: dict[str, int] = {}
    # Left-to-right, top-to-bottom naming so "Window 1" is a stable, human-readable handle.
    for r in sorted(regions, key=lambda r: (r.bbox[1] // 50, r.bbox[0])):
        counters[r.label] = counters.get(r.label, 0) + 1
        r.name = f"{HUMAN[r.label]} {counters[r.label]}"
