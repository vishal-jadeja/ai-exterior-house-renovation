from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.deps import DB, CurrentUser, OwnedProject
from app.models import Design, DesignAssignment, Material, Project, Region
from app.schemas.design import AssignmentsPut, DesignIn, DesignOut

router = APIRouter(tags=["designs"])


async def get_owned_design(design_id: str, db: DB, user: CurrentUser) -> Design:
    d = (
        await db.execute(
            select(Design).options(selectinload(Design.assignments)).where(Design.id == design_id)
        )
    ).scalar_one_or_none()
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Design not found")
    project = await db.get(Project, d.project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Design not found")
    return d


OwnedDesign = Annotated[Design, Depends(get_owned_design)]


async def _load(db: DB, design_id: str) -> Design:
    db.expire_all()  # relationships changed via raw adds/deletes; reload from DB
    return (
        await db.execute(
            select(Design).options(selectinload(Design.assignments)).where(Design.id == design_id)
        )
    ).scalar_one()


@router.get("/projects/{project_id}/designs", response_model=list[DesignOut])
async def list_designs(project: OwnedProject, db: DB):
    rows = await db.execute(
        select(Design)
        .options(selectinload(Design.assignments))
        .where(Design.project_id == project.id)
        .order_by(Design.created_at)
    )
    return rows.scalars().all()


@router.post("/projects/{project_id}/designs", response_model=DesignOut, status_code=201)
async def create_design(body: DesignIn, project: OwnedProject, db: DB):
    count = len((await db.execute(select(Design.id).where(Design.project_id == project.id))).all())
    if count >= 10:
        raise HTTPException(status.HTTP_409_CONFLICT, "Maximum 10 designs per project")
    d = Design(project_id=project.id, name=body.name, is_active=count == 0)
    db.add(d)
    await db.commit()
    return await _load(db, d.id)


@router.patch("/designs/{design_id}", response_model=DesignOut)
async def rename_design(body: DesignIn, design: OwnedDesign, db: DB):
    design.name = body.name
    await db.commit()
    return await _load(db, design.id)


@router.post("/designs/{design_id}/activate", response_model=DesignOut)
async def activate_design(design: OwnedDesign, db: DB):
    siblings = (
        await db.execute(select(Design).where(Design.project_id == design.project_id))
    ).scalars()
    for s in siblings:
        s.is_active = s.id == design.id
    await db.commit()
    return await _load(db, design.id)


@router.post("/designs/{design_id}/clone", response_model=DesignOut, status_code=201)
async def clone_design(design: OwnedDesign, db: DB):
    clone = Design(
        project_id=design.project_id, name=f"{design.name} (copy)"[:120], is_active=False
    )
    db.add(clone)
    await db.flush()
    for a in design.assignments:
        db.add(
            DesignAssignment(
                design_id=clone.id,
                region_id=a.region_id,
                material_id=a.material_id,
                color_hex=a.color_hex,
            )
        )
    await db.commit()
    return await _load(db, clone.id)


@router.delete("/designs/{design_id}", status_code=204)
async def delete_design(design: OwnedDesign, db: DB):
    await db.delete(design)
    await db.commit()


@router.put("/designs/{design_id}/assignments", response_model=DesignOut)
async def put_assignments(body: AssignmentsPut, design: OwnedDesign, db: DB):
    """Replace the region→material map. Validates that regions belong to the project and that the
    material is applicable to the region label."""
    regions = {
        r.id: r
        for r in (
            await db.execute(
                select(Region).where(
                    Region.project_id == design.project_id, Region.is_active.is_(True)
                )
            )
        ).scalars()
    }
    materials = {m.id: m for m in (await db.execute(select(Material))).scalars()}
    seen: set[str] = set()
    for a in design.assignments:
        await db.delete(a)
    for item in body.assignments:
        r = regions.get(item.region_id)
        m = materials.get(item.material_id)
        if r is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown region {item.region_id}"
            )
        if m is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown material {item.material_id}"
            )
        if r.label not in m.applicable_labels:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"{m.name} cannot be applied to a {r.label} ({r.name})",
            )
        if r.id in seen:
            continue
        seen.add(r.id)
        db.add(
            DesignAssignment(
                design_id=design.id, region_id=r.id, material_id=m.id, color_hex=item.color_hex
            )
        )
    await db.commit()
    return await _load(db, design.id)
