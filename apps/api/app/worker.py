"""Job worker: polls the Postgres-backed queue and dispatches to handlers.

Run N replicas for horizontal scale; SKIP LOCKED guarantees a job is claimed once.
"""

from __future__ import annotations

import asyncio
import signal
from datetime import datetime, timezone

from sqlalchemy import select, text

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.models import Job
from app.services.jobs import HANDLERS

settings = get_settings()
configure_logging(settings.log_level)
log = get_logger("worker")


async def _claim_job() -> Job | None:
    async with SessionLocal() as db:
        # Also reclaims jobs whose worker died (locked > 15 min ago while running).
        row = (
            await db.execute(
                text(
                    """
                    UPDATE jobs SET status='running', locked_at=now(), attempts=attempts+1
                    WHERE id = (
                      SELECT id FROM jobs
                      WHERE status='queued'
                         OR (status='running' AND locked_at < now() - interval '15 minutes')
                      ORDER BY created_at
                      FOR UPDATE SKIP LOCKED LIMIT 1)
                    RETURNING id
                    """
                )
            )
        ).first()
        if row is None:
            return None
        await db.commit()
        return (await db.execute(select(Job).where(Job.id == row[0]))).scalar_one()


async def _run_job(job: Job) -> None:
    handler = HANDLERS.get(job.type)
    async with SessionLocal() as db:
        job = await db.get(Job, job.id)
        try:
            if handler is None:
                raise RuntimeError(f"no handler for job type {job.type}")
            result = await handler(db, job)
            job.status = "done"
            job.result = result or {}
            job.error = None
        except Exception as exc:  # noqa: BLE001 - job boundary
            log.exception("job_failed", job_id=job.id, type=job.type, attempts=job.attempts)
            job.error = f"{type(exc).__name__}: {exc}"[:2000]
            job.status = "failed" if job.attempts >= settings.job_max_attempts else "queued"
        job.locked_at = datetime.now(timezone.utc) if job.status == "running" else None
        await db.commit()


async def main() -> None:
    import app.jobs  # noqa: F401  registers handlers

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    log.info("worker_started", handlers=list(HANDLERS))
    while not stop.is_set():
        job = await _claim_job()
        if job is None:
            await asyncio.sleep(settings.worker_poll_seconds)
            continue
        log.info("job_claimed", job_id=job.id, type=job.type)
        await _run_job(job)


if __name__ == "__main__":
    asyncio.run(main())
