from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.deps import DB, CurrentUser
from app.core.ratelimit import limiter
from app.models import Image, Job, Project, Render
from app.providers.storage import s3
from app.routers.designs import OwnedDesign
from app.schemas.render import RenderOut
from app.services.jobs import enqueue

router = APIRouter(tags=["renders"])


async def _out(db: DB, r: Render, job_id: str | None = None) -> RenderOut:
    o = RenderOut.model_validate(r)
    if r.image_id:
        img = await db.get(Image, r.image_id)
        if img:
            o.url = s3.get_storage().presign(img.storage_key)
    o.job_id = job_id
    return o


@router.post("/designs/{design_id}/render", response_model=RenderOut, status_code=202)
@limiter.limit("6/minute")
async def start_render(request: Request, design: OwnedDesign, db: DB, user: CurrentUser):
    if not design.assignments:
        raise HTTPException(status.HTTP_409_CONFLICT, "Assign at least one material first")
    render = Render(design_id=design.id, status="queued")
    db.add(render)
    await db.flush()
    job = await enqueue(
        db,
        "render",
        user.id,
        {"design_id": design.id, "render_id": render.id},
        idempotency_key=f"render:{render.id}",
    )
    return await _out(db, render, job.id)


@router.get("/designs/{design_id}/renders", response_model=list[RenderOut])
async def list_renders(design: OwnedDesign, db: DB):
    rows = (
        await db.execute(
            select(Render).where(Render.design_id == design.id).order_by(Render.created_at.desc())
        )
    ).scalars()
    return [await _out(db, r) for r in rows]


@router.get("/renders/{render_id}", response_model=RenderOut)
async def get_render(render_id: str, db: DB, user: CurrentUser):
    r = await db.get(Render, render_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Render not found")
    design_project = (
        await db.execute(
            select(Project.owner_id)
            .join(Project.designs)
            .where(Project.designs.any(id=r.design_id))
        )
    ).scalar_one_or_none()
    if design_project != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Render not found")
    job = (
        await db.execute(select(Job.id).where(Job.idempotency_key == f"render:{r.id}"))
    ).scalar_one_or_none()
    return await _out(db, r, job)
