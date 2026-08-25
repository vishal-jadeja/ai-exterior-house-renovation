from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class MeasurementsIn(BaseModel):
    facade_width_ft: float | None = Field(default=None, gt=5, lt=300)
    facade_height_ft: float | None = Field(default=None, gt=5, lt=200)
    floors: int | None = Field(default=None, ge=1, le=6)


class RateOut(BaseModel):
    material_id: str
    material_name: str
    category: str
    unit: str
    quantity_unit: str
    material_rate: float
    labor_rate: float
    default_material_rate: float
    default_labor_rate: float
    overridden: bool


class RateIn(BaseModel):
    material_id: str
    material_rate: float = Field(ge=0, le=1_000_000)
    labor_rate: float = Field(ge=0, le=1_000_000)


class RateCardPut(BaseModel):
    rates: list[RateIn] = Field(max_length=100)


class RateCardOut(BaseModel):
    currency: str
    rates: list[RateOut]


class EstimateOut(BaseModel):
    id: str
    design_id: str
    version: int
    currency: str
    grand_total: float
    payload: dict
    created_at: datetime
    # True when regions, assignments, measurements or rates changed after this was computed.
    stale: bool = False

    model_config = {"from_attributes": True}
