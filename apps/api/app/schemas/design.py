from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MaterialOut(BaseModel):
    id: str
    category: str
    name: str
    description: str
    unit: str
    quantity_unit: str
    coverage: float | None
    coats: int
    piece_area_sqft: float | None
    pieces_per_box: int | None
    wastage_pct: float
    default_material_rate: float
    default_labor_rate: float
    currency: str
    texture_key: str | None
    texture_url: str | None = None
    color_hex: str | None
    prompt_hint: str
    applicable_labels: list[str]
    durability_years: int | None
    maintenance: str

    model_config = {"from_attributes": True}


class DesignIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class AssignmentIn(BaseModel):
    region_id: str
    material_id: str
    color_hex: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class AssignmentOut(AssignmentIn):
    id: str

    model_config = {"from_attributes": True}


class AssignmentsPut(BaseModel):
    assignments: list[AssignmentIn] = Field(max_length=200)


class DesignOut(BaseModel):
    id: str
    project_id: str
    name: str
    is_active: bool
    assignments: list[AssignmentOut] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
