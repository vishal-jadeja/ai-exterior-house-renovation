"""Job registry + enqueue helpers. Lives here (not in worker.py) so `python -m app.worker`
and `import app.worker` share one HANDLERS dict."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job

HANDLERS: dict[str, object] = {}


def register(job_type: str):
    def deco(fn):
        HANDLERS[job_type] = fn
        return fn

    return deco


async def enqueue(
    db: AsyncSession,
    job_type: str,
    owner_id: str,
    payload: dict,
    idempotency_key: str | None = None,
) -> Job:
    """Create a queued job. If an identical key is already queued/running, return that job."""
    if idempotency_key:
        existing = (
            await db.execute(
                select(Job).where(
                    Job.idempotency_key == idempotency_key, Job.status.in_(("queued", "running"))
                )
            )
        ).scalar_one_or_none()
        if existing:
            return existing
        # Allow re-running once the earlier job finished: retire the old key.
        old = (
            await db.execute(select(Job).where(Job.idempotency_key == idempotency_key))
        ).scalar_one_or_none()
        if old:
            old.idempotency_key = None
    job = Job(type=job_type, owner_id=owner_id, payload=payload, idempotency_key=idempotency_key)
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job
