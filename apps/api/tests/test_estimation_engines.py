import numpy as np
import pytest

from app.services import area_estimator, cost_engine, quantity_engine, scale_estimator

WALL = {
    "id": "w",
    "label": "wall",
    "name": "Wall 1",
    "polygon": [[0, 0], [1000, 0], [1000, 500], [0, 500]],
    "bbox": [0, 0, 1000, 500],
    "confidence": 0.9,
}
DOOR = {
    "id": "d",
    "label": "door",
    "name": "Door 1",
    "polygon": [[450, 300], [550, 300], [550, 500], [450, 500]],
    "bbox": [450, 300, 100, 200],
    "confidence": 0.8,
}
WIN = {
    "id": "n",
    "label": "window",
    "name": "Window 1",
    "polygon": [[100, 100], [200, 100], [200, 220], [100, 220]],
    "bbox": [100, 100, 100, 120],
    "confidence": 0.8,
}
RAIL = {
    "id": "r",
    "label": "railing",
    "name": "Railing 1",
    "polygon": [[600, 50], [900, 50], [900, 80], [600, 80]],
    "bbox": [600, 50, 300, 30],
    "confidence": 0.7,
}


def test_scale_prefers_user_measurement():
    s = scale_estimator.estimate([WALL, DOOR], 1000, facade_width_ft=40)
    assert s.method == "user_measurement" and s.confidence == "high"
    assert s.ft_per_px == pytest.approx(0.04)


def test_scale_uses_door_then_window_then_default():
    s = scale_estimator.estimate([WALL, DOOR], 1000)
    assert s.method == "door_reference" and s.ft_per_px == pytest.approx(7 / 200)
    s = scale_estimator.estimate([WALL, WIN, dict(WIN, id="n2", bbox=[300, 100, 100, 100])], 1000)
    assert s.method == "window_reference" and s.ft_per_px == pytest.approx(4 / 110)
    s = scale_estimator.estimate([WALL], 1000, floors=2)
    assert s.method == "floor_count" and s.ft_per_px == pytest.approx(20 / 500)
    s = scale_estimator.estimate([WALL], 1000)
    assert s.method == "default_assumption" and s.confidence == "low"


def test_area_subtracts_openings_and_measures_lengths():
    ft = 7 / 200  # door reference
    m = {x.region_id: x for x in area_estimator.measure([WALL, DOOR, WIN, RAIL], ft, 1000, 500)}
    wall = m["w"]
    gross_sqft = 1000 * 500 * ft**2
    openings_sqft = (100 * 200 + 100 * 120 + 300 * 30) * ft**2
    assert wall.area_sqft == pytest.approx(gross_sqft - openings_sqft, rel=0.02)
    assert "openings subtracted" in wall.notes[0]
    assert m["r"].length_ft == pytest.approx(300 * ft, rel=0.01)
    assert m["d"].area_sqft == pytest.approx(100 * 200 * ft**2, rel=0.02)


PAINT = {
    "id": "p",
    "name": "Paint",
    "category": "paint",
    "unit": "sqft",
    "quantity_unit": "litre",
    "coverage": 100,
    "coats": 2,
    "wastage_pct": 5,
}
TILE = {
    "id": "t",
    "name": "Tile",
    "category": "tile",
    "unit": "sqft",
    "quantity_unit": "piece",
    "piece_area_sqft": 2,
    "pieces_per_box": 8,
    "wastage_pct": 10,
}
RAILING = {
    "id": "g",
    "name": "Glass",
    "category": "railing",
    "unit": "rft",
    "quantity_unit": "rft",
    "wastage_pct": 0,
}


def test_quantities():
    q = quantity_engine.compute(PAINT, 1000, None)
    assert q.with_wastage == 1050 and q.quantity == 21.0 and q.packs == 3  # 21 L → 3 × 10 L
    q = quantity_engine.compute(TILE, 100, None)
    assert q.quantity == 56 and q.packs == 7  # 110 sqft / 2 = 55 pcs → 7 boxes = 56 bought
    q = quantity_engine.compute(RAILING, 999, 20)
    assert q.base == 20 and q.quantity == 20 and q.packs == 5  # posts every 5 ft + 1


def test_cost_totals_and_categories():
    qp = quantity_engine.compute(PAINT, 1000, None)
    qr = quantity_engine.compute(RAILING, 0, 20)
    est = cost_engine.price(
        [
            (WALL, qp, {"material_rate": 400, "labor_rate": 15}),
            (RAIL, qr, {"material_rate": 1500, "labor_rate": 250}),
        ],
        "INR",
    )
    assert est["lines"][0]["material_cost"] == 21 * 400
    assert est["lines"][0]["labor_cost"] == 1000 * 15
    assert est["lines"][1]["total"] == 20 * 1500 + 20 * 250
    assert est["grand_total"] == 21 * 400 + 15000 + 35000
    assert {c["category"] for c in est["categories"]} == {"paint", "railing"}
    # editing a rate changes the total deterministically
    est2 = cost_engine.price([(WALL, qp, {"material_rate": 500, "labor_rate": 15})], "INR")
    assert est2["grand_total"] == 21 * 500 + 15000
    # category totals must sum back to the grand total
    assert sum(c["total"] for c in est["categories"]) == est["grand_total"]


def test_foreshortening_axis_aligned_is_one_trapezoid_is_more():
    rect = np.array(WALL["polygon"], np.float32)
    assert area_estimator._foreshortening(rect) == 1.0
    trapezoid = np.array([[0, 0], [1000, 100], [1000, 400], [0, 500]], np.float32)
    assert area_estimator._foreshortening(trapezoid) > 1.0


def test_balcony_gets_a_length_and_nonzero_railing_cost():
    balcony = dict(RAIL, id="b", label="balcony", name="Balcony 1")
    ft = 7 / 200
    m = {x.region_id: x for x in area_estimator.measure([WALL, DOOR, balcony], ft, 1000, 500)}
    assert m["b"].length_ft is not None and m["b"].length_ft > 0
    q = quantity_engine.compute(RAILING, 0, m["b"].length_ft)
    est = cost_engine.price([(balcony, q, {"material_rate": 1450, "labor_rate": 260})], "INR")
    assert est["grand_total"] > 0


def test_pillar_area_is_height_times_width_plus_two_depths():
    ft = 1.0
    pillar = {
        "id": "pi",
        "label": "pillar",
        "name": "Pillar 1",
        "polygon": [[0, 0], [50, 0], [50, 300], [0, 300]],
        "bbox": [0, 0, 50, 300],
        "confidence": 0.8,
    }
    m = {x.region_id: x for x in area_estimator.measure([pillar], ft, 1000, 500)}
    assert m["pi"].area_sqft == pytest.approx(300 * (50 + 2), rel=0.001)


def test_sloped_railing_polyline_length_exceeds_bbox_width():
    ft = 1.0
    sloped = {
        "id": "sr",
        "label": "railing",
        "name": "Sloped railing",
        "polygon": [[0, 80], [280, 0], [300, 20], [20, 100]],
        "bbox": [0, 0, 300, 100],
        "confidence": 0.8,
    }
    m = {x.region_id: x for x in area_estimator.measure([sloped], ft, 1000, 500)}
    assert m["sr"].length_ft > sloped["bbox"][2] * ft


def test_user_width_and_height_scale_uses_geometric_mean():
    s = scale_estimator.estimate([WALL], 1000, facade_width_ft=40, facade_height_ft=20)
    sil_w, sil_h = 1000.0, 500.0
    expected = ((40 / sil_w) * (20 / sil_h)) ** 0.5
    assert s.method == "user_measurement" and s.ft_per_px == pytest.approx(expected)
