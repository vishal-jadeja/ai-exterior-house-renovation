from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.deps import DB, CurrentUser
from app.core.ratelimit import limiter
from app.models import Design, Estimate, Image, Job, Project, Report
from app.providers.storage import s3
from app.routers.designs import OwnedDesign
from app.schemas.report import ReportOut
from app.services.jobs import enqueue

router = APIRouter(tags=["reports"])


async def _out(db: DB, r: Report, job_id: str | None = None) -> ReportOut:
    o = ReportOut.model_validate(r)
    if r.image_id:
        img = await db.get(Image, r.image_id)
        if img:
            o.url = s3.get_storage().presign(img.storage_key, filename="renovation-estimate.pdf")
    o.job_id = job_id
    return o


@router.post("/designs/{design_id}/report", response_model=ReportOut, status_code=202)
@limiter.limit("6/minute")
async def start_report(request: Request, design: OwnedDesign, db: DB, user: CurrentUser):
    has_estimate = (
        await db.execute(select(Estimate.id).where(Estimate.design_id == design.id).limit(1))
    ).scalar_one_or_none()
    if not has_estimate:
        raise HTTPException(status.HTTP_409_CONFLICT, "Calculate an estimate first")
    report = Report(design_id=design.id, status="queued")
    db.add(report)
    await db.flush()
    job = await enqueue(
        db,
        "report",
        user.id,
        {"design_id": design.id, "report_id": report.id},
        idempotency_key=f"report:{report.id}",
    )
    return await _out(db, report, job.id)


@router.get("/designs/{design_id}/reports", response_model=list[ReportOut])
async def list_reports(design: OwnedDesign, db: DB):
    rows = (
        await db.execute(
            select(Report).where(Report.design_id == design.id).order_by(Report.created_at.desc())
        )
    ).scalars()
    return [await _out(db, r) for r in rows]


@router.get("/reports/{report_id}", response_model=ReportOut)
async def get_report(report_id: str, db: DB, user: CurrentUser):
    r = await db.get(Report, report_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    owner = (
        await db.execute(
            select(Project.owner_id)
            .join(Design, Design.project_id == Project.id)
            .where(Design.id == r.design_id)
        )
    ).scalar_one_or_none()
    if owner != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Report not found")
    job = (
        await db.execute(select(Job.id).where(Job.idempotency_key == f"report:{r.id}"))
    ).scalar_one_or_none()
    return await _out(db, r, job)
