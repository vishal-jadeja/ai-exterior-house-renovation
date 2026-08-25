from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.services.taxonomy import LABELS

Label = Literal[
    "wall", "window", "door", "balcony", "railing", "pillar", "parapet", "gate", "roof_edge"
]


class RegionOut(BaseModel):
    id: str
    image_id: str
    label: str
    name: str
    polygon: list[list[float]]
    pixel_area: float
    bbox: list[float]
    confidence: float
    source: str
    version: int
    is_active: bool

    model_config = {"from_attributes": True}


class RegionIn(BaseModel):
    """A region as edited in the browser. `id` is None for newly drawn regions."""

    id: str | None = None
    label: Label
    name: str = Field(default="", max_length=64)
    polygon: list[list[float]] = Field(min_length=3, max_length=400)
    is_active: bool = True

    @field_validator("polygon")
    @classmethod
    def _finite(cls, v):
        for p in v:
            if len(p) != 2:
                raise ValueError("polygon points must be [x, y]")
        return v


class RegionsPut(BaseModel):
    regions: list[RegionIn] = Field(max_length=200)


class JobOut(BaseModel):
    id: str
    type: str
    status: str
    error: str | None
    result: dict | None
    attempts: int

    model_config = {"from_attributes": True}


assert set(Label.__args__) == set(LABELS)
