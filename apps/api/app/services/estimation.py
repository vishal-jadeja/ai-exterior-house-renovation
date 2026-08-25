"""Orchestrates scale → area → quantity → cost for a design. Pure given loaded rows."""

from __future__ import annotations

from app.services import area_estimator, cost_engine, quantity_engine, scale_estimator


def region_dict(r) -> dict:
    return {
        "id": r.id,
        "label": r.label,
        "name": r.name,
        "polygon": r.polygon,
        "bbox": r.bbox,
        "confidence": r.confidence,
        "source": r.source,
    }


def material_dict(m) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "category": m.category,
        "unit": m.unit,
        "quantity_unit": m.quantity_unit,
        "coverage": m.coverage,
        "coats": m.coats,
        "piece_area_sqft": m.piece_area_sqft,
        "pieces_per_box": m.pieces_per_box,
        "wastage_pct": m.wastage_pct,
    }


def estimate_design(
    project,
    regions: list[dict],
    assignments: list[tuple[str, str]],
    materials: dict[str, dict],
    rates: dict[str, dict],
    image_w: int,
    image_h: int,
) -> dict:
    """assignments: (region_id, material_id). rates: material_id → {material_rate, labor_rate}."""
    scale = scale_estimator.estimate(
        regions, image_w, project.facade_width_ft, project.facade_height_ft, project.floors
    )
    measures = {
        m.region_id: m for m in area_estimator.measure(regions, scale.ft_per_px, image_w, image_h)
    }
    by_id = {r["id"]: r for r in regions}
    lines = []
    for region_id, material_id in assignments:
        r, m, sm = by_id.get(region_id), materials.get(material_id), measures.get(region_id)
        if r is None or m is None or sm is None:
            continue
        q = quantity_engine.compute(m, sm.area_sqft, sm.length_ft)
        lines.append((r, q, rates[material_id]))
    priced = cost_engine.price(lines, project.currency)
    priced["scale"] = {
        "ft_per_px": scale.ft_per_px,
        "method": scale.method,
        "confidence": scale.confidence,
        "assumptions": scale.assumptions,
    }
    priced["surfaces"] = [m.as_dict() for m in measures.values()]
    priced["assumptions"] = scale.assumptions + [
        "Areas are derived from a single photo and are approximate (±15–25%).",
        "Quantities include the catalog wastage allowance per material.",
        "Labour rates are per unit of surface; material rates per unit of material quantity.",
        "Estimates are advisory and not a binding quotation.",
    ]
    return priced
