import numpy as np

from app.services.region_mapper import extract_regions, polygon_area, rasterize
from app.services.taxonomy import LABELS


def _lm(h=600, w=800):
    lm = np.full((h, w), -1, np.int16)
    lm[100:550, 50:750] = LABELS.index("wall")
    lm[200:300, 100:200] = LABELS.index("window")
    lm[200:300, 300:400] = LABELS.index("window")
    lm[350:540, 350:450] = LABELS.index("door")
    lm[150:190, 500:700] = LABELS.index("railing")
    lm[400:440, 500:650] = LABELS.index("balcony")
    return lm


def test_extract_regions_finds_each_label():
    regs = extract_regions(_lm())
    labels = {r.label for r in regs}
    assert {"wall", "window", "door", "railing", "balcony", "roof_edge"} <= labels
    # the CMP model's own "balcony" class must map straight through, not get folded into railing
    balconies = [r for r in regs if r.label == "balcony"]
    assert len(balconies) == 1 and balconies[0].pixel_area > 0
    windows = [r for r in regs if r.label == "window"]
    assert len(windows) == 2
    assert all(abs(r.pixel_area - 100 * 100) < 500 for r in windows)
    assert {r.name for r in windows} == {"Window 1", "Window 2"}


def test_tiny_blobs_are_dropped():
    lm = _lm()
    lm[10:12, 10:12] = LABELS.index("window")
    regs = extract_regions(lm)
    assert len([r for r in regs if r.label == "window"]) == 2


def test_polygon_area_and_rasterize_agree():
    poly = [[10, 10], [110, 10], [110, 60], [10, 60]]
    assert polygon_area(poly) == 5000
    assert abs(int(rasterize(poly, 100, 200).sum()) - 5000) < 300
