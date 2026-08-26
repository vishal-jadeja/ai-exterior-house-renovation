from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class Relabel(BaseModel):
    id: str
    label: str


class Addition(BaseModel):
    label: str
    bbox: list[float] = Field(min_length=4, max_length=4)  # normalised x0,y0,x1,y1 in [0,1]
    name: str | None = None


class Refinement(BaseModel):
    relabels: list[Relabel] = []
    additions: list[Addition] = []
    floors: int | None = Field(default=None, ge=1, le=6)
    door_height_ft: float | None = Field(default=None, ge=5.5, le=9)
    notes: str | None = None


class DetectedRegion(BaseModel):
    label: str
    bbox: list[float] = Field(min_length=4, max_length=4)  # normalised x0,y0,x1,y1 in [0,1]
    name: str | None = None


class Detection(BaseModel):
    """Full primary detection when a hosted vision model stands in for the local segmenter."""

    regions: list[DetectedRegion] = []
    floors: int | None = Field(default=None, ge=1, le=6)
    door_height_ft: float | None = Field(default=None, ge=5.5, le=9)
    notes: str | None = None


class VisionRefiner(Protocol):
    name: str

    async def refine(self, jpeg: bytes, regions: list[dict]) -> Refinement | None: ...

    async def detect(self, jpeg: bytes) -> Detection | None: ...


class NoopRefiner:
    name = "noop"

    async def refine(self, jpeg: bytes, regions: list[dict]) -> Refinement | None:
        return None

    async def detect(self, jpeg: bytes) -> Detection | None:
        return None
