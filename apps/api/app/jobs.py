"""Job handlers. Each is `async (db, job) -> dict`. Registered on import by the worker."""

from __future__ import annotations

from app.worker import register


@register("noop")
async def noop(db, job):
    return {"ok": True}
