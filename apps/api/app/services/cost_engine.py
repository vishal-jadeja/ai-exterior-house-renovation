"""Cost estimate (spec 5.7): material + labour per line, per category, grand total.

Pure and deterministic — re-run instantly whenever a rate changes. Rates come from the project's
rate card (user overrides) falling back to the catalog defaults.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.services.quantity_engine import Quantity


@dataclass
class Line:
    region_id: str
    region_name: str
    label: str
    material_id: str
    material_name: str
    category: str
    surface: float
    surface_unit: str
    quantity: float
    quantity_unit: str
    packs: int | None
    pack_label: str | None
    material_rate: float
    labor_rate: float
    material_cost: float
    labor_cost: float
    total: float
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def price(lines_in: list[tuple[dict, Quantity, dict]], currency: str) -> dict:
    """lines_in: (region_dict, quantity, rates{material_rate, labor_rate}) → estimate payload."""
    lines: list[Line] = []
    categories: dict[str, dict] = {}
    for region, q, rates in lines_in:
        mr, lr = float(rates["material_rate"]), float(rates["labor_rate"])
        mcost = round(q.quantity * mr, 2)
        lcost = round(q.base * lr, 2)
        line = Line(
            region_id=region["id"],
            region_name=region["name"],
            label=region["label"],
            material_id=q.material_id,
            material_name=q.material_name,
            category=q.category,
            surface=q.base,
            surface_unit=q.unit,
            quantity=q.quantity,
            quantity_unit=q.quantity_unit,
            packs=q.packs,
            pack_label=q.pack_label,
            material_rate=mr,
            labor_rate=lr,
            material_cost=mcost,
            labor_cost=lcost,
            total=round(mcost + lcost, 2),
            notes=list(q.breakdown),
        )
        lines.append(line)
        c = categories.setdefault(
            q.category,
            {"category": q.category, "material_cost": 0.0, "labor_cost": 0.0, "total": 0.0},
        )
        c["material_cost"] = round(c["material_cost"] + mcost, 2)
        c["labor_cost"] = round(c["labor_cost"] + lcost, 2)
        c["total"] = round(c["total"] + mcost + lcost, 2)
    material_total = round(sum(line.material_cost for line in lines), 2)
    labor_total = round(sum(line.labor_cost for line in lines), 2)
    return {
        "currency": currency,
        "lines": [line.as_dict() for line in lines],
        "categories": sorted(categories.values(), key=lambda c: -c["total"]),
        "material_total": material_total,
        "labor_total": labor_total,
        "grand_total": round(material_total + labor_total, 2),
    }
