"""Render provider contract (spec 5.4).

A provider receives the sanitised photo, one entry per assigned region (polygon in pixel space +
material spec) and returns the redesigned photo. Providers must preserve pixels outside masks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np


@dataclass
class RenderRegion:
    region_id: str
    label: str
    name: str
    polygon: list[list[float]]
    material_id: str
    category: str  # paint|texture|cladding|tile|railing|panel|gate
    material_name: str
    prompt_hint: str
    texture: np.ndarray | None  # RGB uint8 tile, or None
    color_hex: str | None


@dataclass
class RenderRequest:
    rgb: np.ndarray  # HxWx3 uint8
    regions: list[RenderRegion]
    px_per_ft: float  # for texture scale; approximate is fine
    holes: list[list[list[float]]] = field(default_factory=list)  # openings cut out of surfaces
    log: list[dict] = field(default_factory=list)


class RenderProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    async def render(self, req: RenderRequest) -> np.ndarray: ...


class ProviderUnavailable(RuntimeError):
    """Raised when a provider cannot serve (missing key, quota, upstream error) → try next."""
