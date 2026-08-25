from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class RenderOut(BaseModel):
    id: str
    design_id: str
    status: str
    provider_used: str | None
    provider_log: list
    error: str | None
    url: str | None = None
    job_id: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
