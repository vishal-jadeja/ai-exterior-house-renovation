from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from app.core.deps import DB, CurrentUser, OwnedProject
from app.core.ratelimit import limiter
from app.models import Image, Region
from app.schemas.region import JobOut, RegionOut, RegionsPut
from app.services.jobs import enqueue
from app.services.region_mapper import polygon_area
from app.services.taxonomy import HUMAN

router = APIRouter(prefix="/projects/{project_id}", tags=["regions"])

MIN_REGION_PX = 16.0  # smallest polygon area (px²) we accept from the editor


async def _source_image(db: DB, project_id: str) -> Image:
    img = (
        (
            await db.execute(
                select(Image)
                .where(Image.project_id == project_id, Image.kind == "sanitized")
                .order_by(Image.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if img is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Upload a house photo first")
    return img


@router.post("/segment", response_model=JobOut, status_code=202)
@limiter.limit("10/minute")
async def segment(request: Request, project: OwnedProject, db: DB, user: CurrentUser):
    img = await _source_image(db, project.id)
    # Status must be committed *with* (not after) the job row: a free worker can otherwise
    # finish and write "segmented" before this handler's later commit overwrites it.
    project.status = "segmenting"
    return await enqueue(
        db,
        "segment",
        user.id,
        {"project_id": project.id, "image_id": img.id},
        idempotency_key=f"segment:{img.id}",
    )


@router.get("/regions", response_model=list[RegionOut])
async def list_regions(project: OwnedProject, db: DB):
    rows = await db.execute(
        select(Region)
        .where(Region.project_id == project.id, Region.is_active.is_(True))
        .order_by(Region.created_at)
    )
    return rows.scalars().all()


@router.put("/regions", response_model=list[RegionOut])
async def put_regions(body: RegionsPut, project: OwnedProject, db: DB):
    """Bulk replace the user's view of regions. Existing IDs are updated (version+1, source=user),
    unknown IDs are ignored, missing IDs are deactivated, new entries (id=None) are created."""
    img = await _source_image(db, project.id)
    w, h = img.width or 10_000, img.height or 10_000
    existing = {
        r.id: r
        for r in (await db.execute(select(Region).where(Region.project_id == project.id))).scalars()
    }
    seen: set[str] = set()
    counters: dict[str, int] = {}
    out: list[Region] = []
    for item in body.regions:
        poly = [[min(max(float(x), 0), w), min(max(float(y), 0), h)] for x, y in item.polygon]
        xs, ys = [p[0] for p in poly], [p[1] for p in poly]
        bbox = [min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)]
        area = polygon_area(poly)
        if area < MIN_REGION_PX or bbox[2] < 1 or bbox[3] < 1:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Region '{item.name or item.label}' is too small or degenerate to measure",
            )
        counters[item.label] = counters.get(item.label, 0) + 1
        name = item.name.strip() or f"{HUMAN[item.label]} {counters[item.label]}"
        if item.id and item.id in existing:
            r = existing[item.id]
            changed = (
                r.label != item.label or r.polygon != poly or r.name != name or not r.is_active
            )
            if changed:
                r.version += 1
                r.source = "user"
                r.confidence = 1.0
            r.label, r.polygon, r.bbox, r.pixel_area, r.name, r.is_active = (
                item.label,
                poly,
                bbox,
                area,
                name,
                item.is_active,
            )
            seen.add(r.id)
            out.append(r)
        elif item.id is None:
            r = Region(
                project_id=project.id,
                image_id=img.id,
                label=item.label,
                name=name,
                polygon=poly,
                pixel_area=area,
                bbox=bbox,
                confidence=1.0,
                source="user",
                version=1,
                is_active=item.is_active,
            )
            db.add(r)
            out.append(r)
    for rid, r in existing.items():
        if rid not in seen and r.is_active:
            r.is_active = False
            r.version += 1
    # Only advance the workflow; never pull a rendered/estimated project back a step.
    if project.status in ("created", "uploaded", "segmenting", "segmented"):
        project.status = "regions_reviewed"
    await db.commit()
    for r in out:
        await db.refresh(r)
    return [r for r in out if r.is_active]


@router.delete("/regions/{region_id}", status_code=204)
async def delete_region(region_id: str, project: OwnedProject, db: DB):
    r = await db.get(Region, region_id)
    if r is None or r.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Region not found")
    r.is_active = False
    r.version += 1
    await db.commit()
