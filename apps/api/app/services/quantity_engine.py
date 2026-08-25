"""Material quantities from surface measures (spec 5.6). Pure; no I/O."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

PAINT_PACK_L = 10
TEXTURE_BAG_KG = 25
RAILING_POST_SPACING_FT = 5.0


@dataclass
class Quantity:
    material_id: str
    material_name: str
    category: str
    unit: str  # surface unit the labour is priced on (sqft | rft)
    base: float  # net surface (sqft or rft) before wastage
    wastage_pct: float
    with_wastage: float
    quantity: float  # in quantity_unit
    quantity_unit: str
    packs: int | None
    pack_label: str | None
    breakdown: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def compute(material: dict, area_sqft: float, length_ft: float | None) -> Quantity:
    unit = material["unit"]
    base = float(length_ft or 0.0) if unit == "rft" else float(area_sqft)
    wastage = float(material.get("wastage_pct") or 0.0)
    ww = base * (1 + wastage / 100.0)
    qunit = material.get("quantity_unit") or "sqft"
    coverage = material.get("coverage")
    coats = int(material.get("coats") or 1)
    piece = material.get("piece_area_sqft")
    per_box = material.get("pieces_per_box")
    notes: list[str] = []
    packs = None
    pack_label = None

    if qunit == "litre":
        qty = ww * coats / float(coverage or 100.0)
        packs = math.ceil(qty / PAINT_PACK_L) if qty > 0 else 0
        pack_label = f"{PAINT_PACK_L} L cans"
        notes.append(f"{coats} coat(s) at {coverage:g} sqft/L per coat")
    elif qunit == "kg":
        qty = ww * coats / float(coverage or 25.0)
        packs = math.ceil(qty / TEXTURE_BAG_KG) if qty > 0 else 0
        pack_label = f"{TEXTURE_BAG_KG} kg bags"
        notes.append(f"coverage {coverage:g} sqft/kg")
    elif qunit == "piece":
        qty = math.ceil(round(ww / float(piece or 1.0), 6)) if ww > 0 else 0
        if per_box:
            packs = math.ceil(qty / per_box)
            pack_label = f"boxes of {per_box}"
        notes.append(f"piece size {piece:g} sqft")
    elif qunit == "sheet":
        qty = math.ceil(round(ww / float(piece or 32.0), 6)) if ww > 0 else 0
        packs = qty
        pack_label = "sheets"
        notes.append(f"sheet size {piece:g} sqft")
    elif qunit == "rft":
        qty = ww
        packs = math.ceil(base / RAILING_POST_SPACING_FT) + 1 if base > 0 else 0
        pack_label = f"posts @ {RAILING_POST_SPACING_FT:g} ft"
    else:  # sqft
        qty = ww
    if wastage:
        notes.append(f"{wastage:g}% wastage added")
    return Quantity(
        material_id=material["id"],
        material_name=material["name"],
        category=material["category"],
        unit=unit,
        base=round(base, 1),
        wastage_pct=wastage,
        with_wastage=round(ww, 1),
        quantity=round(qty, 2),
        quantity_unit=qunit,
        packs=packs,
        pack_label=pack_label,
        breakdown=notes,
    )
