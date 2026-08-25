from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProjectIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    currency: str = Field(default="INR", min_length=3, max_length=8)


class ProjectPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    currency: str | None = Field(default=None, min_length=3, max_length=8)


class ProjectOut(BaseModel):
    id: str
    name: str
    currency: str
    unit_system: str
    status: str
    scale_ft_per_px: float | None
    scale_method: str | None
    scale_confidence: str | None
    facade_width_ft: float | None
    facade_height_ft: float | None
    floors: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ImageOut(BaseModel):
    id: str
    kind: str
    width: int | None
    height: int | None
    quality_score: float | None
    meta: dict
    url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class QualityOut(BaseModel):
    usable: bool
    score: float
    blur_score: float
    brightness: float
    contrast: float
    guidance: list[str]


class UploadOut(BaseModel):
    image: ImageOut
    quality: QualityOut
    # Regions of the previous photo that were deactivated by this upload (0 on first upload).
    replaced_regions: int = 0
