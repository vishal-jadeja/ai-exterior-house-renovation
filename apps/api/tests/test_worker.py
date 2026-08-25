"""Worker loop unit tests. `_claim_job` issues Postgres-only SQL (FOR UPDATE SKIP LOCKED,
now() - interval …) so it is not exercised here — only against the real Postgres CI service."""

from __future__ import annotations

from app.core import db as dbmod
from app.models import Job
from app.services.jobs import HANDLERS
from app.worker import _backoff_seconds, _run_job


def test_backoff_seconds_doubles_then_caps():
    assert _backoff_seconds(1) == 5
    assert _backoff_seconds(2) == 10
    assert _backoff_seconds(3) == 20
    assert _backoff_seconds(4) == 40
    assert _backoff_seconds(20) == 120  # capped at 2 minutes


async def _bad_handler(db, job):
    """Leaves the session in a failed transaction, then raises — the worst case a handler
    can hand back to `_run_job`. Two fresh rows sharing an idempotency_key violate its unique
    constraint (unrelated to the job being processed, so its identity map entry stays clean)."""
    db.add(Job(type="x", status="queued", payload={}, owner_id="u", idempotency_key="dup-key"))
    db.add(Job(type="x", status="queued", payload={}, owner_id="u", idempotency_key="dup-key"))
    await db.flush()
    raise AssertionError("unreachable")


async def _make_job(attempts: int) -> Job:
    async with dbmod.SessionLocal() as s:
        job = Job(type="flaky", status="running", payload={}, owner_id="u", attempts=attempts)
        s.add(job)
        await s.commit()
        await s.refresh(job)
        return job


async def test_run_job_requeues_when_attempts_below_max(client, monkeypatch):  # noqa: F811
    # worker.py binds `SessionLocal` at import time (`from app.core.db import SessionLocal`),
    # so the `client` fixture's swap of `dbmod.SessionLocal` doesn't reach it on its own.
    monkeypatch.setattr("app.worker.SessionLocal", dbmod.SessionLocal)
    monkeypatch.setitem(HANDLERS, "flaky", _bad_handler)
    job = await _make_job(attempts=1)
    await _run_job(job)  # must not raise — the worker loop stays alive
    async with dbmod.SessionLocal() as s:
        reloaded = await s.get(Job, job.id)
    assert reloaded.status == "queued"
    assert reloaded.error and "IntegrityError" in reloaded.error
    assert reloaded.locked_at is None
    assert reloaded.created_at > job.created_at  # pushed forward by the backoff delay


async def test_run_job_marks_failed_at_max_attempts(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr("app.worker.SessionLocal", dbmod.SessionLocal)
    monkeypatch.setitem(HANDLERS, "flaky", _bad_handler)
    job = await _make_job(attempts=3)  # settings.job_max_attempts default is 3
    await _run_job(job)
    async with dbmod.SessionLocal() as s:
        reloaded = await s.get(Job, job.id)
    assert reloaded.status == "failed"


async def test_run_job_no_handler_leaves_job_queued_or_failed(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr("app.worker.SessionLocal", dbmod.SessionLocal)
    job = await _make_job(attempts=1)
    await _run_job(job)
    async with dbmod.SessionLocal() as s:
        reloaded = await s.get(Job, job.id)
    assert reloaded.status in ("queued", "failed")
    assert "no handler" in (reloaded.error or "")
