from __future__ import annotations

import asyncio
import hashlib
import json

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import DB, OwnedProject
from app.models import Design, Estimate, Image, Material, Project, RateCard, Region
from app.routers.designs import OwnedDesign
from app.schemas.estimate import EstimateOut, MeasurementsIn, RateCardOut, RateCardPut, RateOut
from app.schemas.project import ProjectOut
from app.services import scale_estimator
from app.services.estimation import estimate_design, material_dict, region_dict

router = APIRouter(tags=["estimates"])


async def _regions(db: AsyncSession, project_id: str) -> list[dict]:
    rows = (
        await db.execute(
            select(Region).where(Region.project_id == project_id, Region.is_active.is_(True))
        )
    ).scalars()
    return [region_dict(r) for r in rows]


async def _image(db: AsyncSession, project_id: str) -> Image:
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


async def _rates(db: AsyncSession, project: Project) -> tuple[dict[str, dict], list[RateOut]]:
    materials = (
        await db.execute(select(Material).order_by(Material.category, Material.name))
    ).scalars()
    overrides = {
        rc.material_id: rc
        for rc in (
            await db.execute(select(RateCard).where(RateCard.project_id == project.id))
        ).scalars()
    }
    rates: dict[str, dict] = {}
    out: list[RateOut] = []
    for m in materials:
        o = overrides.get(m.id)
        mr = o.material_rate if o else m.default_material_rate
        lr = o.labor_rate if o else m.default_labor_rate
        rates[m.id] = {"material_rate": mr, "labor_rate": lr}
        out.append(
            RateOut(
                material_id=m.id,
                material_name=m.name,
                category=m.category,
                unit=m.unit,
                quantity_unit=m.quantity_unit,
                material_rate=mr,
                labor_rate=lr,
                default_material_rate=m.default_material_rate,
                default_labor_rate=m.default_labor_rate,
                overridden=o is not None,
            )
        )
    return rates, out


def _fingerprint(
    project: Project, regions: list[dict], assignments: list[tuple[str, str]], rates: dict
) -> str:
    """Hash of every input an estimate depends on. Stored in the payload; when the current
    inputs hash differently the stored estimate is stale and must be recalculated."""
    used = sorted({m for _, m in assignments})
    doc = {
        "measurements": [project.facade_width_ft, project.facade_height_ft, project.floors],
        "currency": project.currency,
        "regions": sorted((r["id"], r["label"], r["polygon"]) for r in regions),
        "assignments": sorted(assignments),
        "rates": {m: rates[m] for m in used if m in rates},
    }
    return hashlib.sha256(json.dumps(doc, sort_keys=True, default=str).encode()).hexdigest()


async def current_fingerprint(db: AsyncSession, design: Design) -> str:
    project = await db.get(Project, design.project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    regions = await _regions(db, project.id)
    rates, _ = await _rates(db, project)
    return _fingerprint(
        project, regions, [(a.region_id, a.material_id) for a in design.assignments], rates
    )


async def latest_estimate_row(db: AsyncSession, design_id: str) -> Estimate | None:
    return (
        (
            await db.execute(
                select(Estimate)
                .where(Estimate.design_id == design_id)
                .order_by(Estimate.version.desc())
            )
        )
        .scalars()
        .first()
    )


async def _with_stale(db: AsyncSession, design: Design, est: Estimate) -> EstimateOut:
    out = EstimateOut.model_validate(est)
    out.stale = est.payload.get("fingerprint") != await current_fingerprint(db, design)
    return out


@router.patch("/projects/{project_id}/measurements", response_model=ProjectOut)
async def set_measurements(body: MeasurementsIn, project: OwnedProject, db: DB):
    """Optional user measurements (spec 5.5). Only fields present in the body are changed;
    send an explicit null to clear one. Recomputes and stores the project scale."""
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(project, k, v)
    img = await _image(db, project.id)
    regions = await _regions(db, project.id)
    s = scale_estimator.estimate(
        regions,
        img.width or 1000,
        project.facade_width_ft,
        project.facade_height_ft,
        project.floors,
    )
    project.scale_ft_per_px, project.scale_method, project.scale_confidence = (
        s.ft_per_px,
        s.method,
        s.confidence,
    )
    await db.commit()
    await db.refresh(project)
    return project


@router.get("/projects/{project_id}/rate-card", response_model=RateCardOut)
async def get_rate_card(project: OwnedProject, db: DB):
    _, out = await _rates(db, project)
    return RateCardOut(currency=project.currency, rates=out)


@router.put("/projects/{project_id}/rate-card", response_model=RateCardOut)
async def put_rate_card(body: RateCardPut, project: OwnedProject, db: DB):
    """Upsert per-project rate overrides (spec 5.7 'modify material rates'). Existing estimates
    are not rewritten; they report `stale=true` until recalculated."""
    materials = set((await db.execute(select(Material.id))).scalars())
    existing = {
        rc.material_id: rc
        for rc in (
            await db.execute(select(RateCard).where(RateCard.project_id == project.id))
        ).scalars()
    }
    for item in body.rates:
        if item.material_id not in materials:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown material")
        rc = existing.get(item.material_id)
        if rc:
            rc.material_rate, rc.labor_rate = item.material_rate, item.labor_rate
        else:
            db.add(
                RateCard(
                    project_id=project.id,
                    material_id=item.material_id,
                    material_rate=item.material_rate,
                    labor_rate=item.labor_rate,
                    currency=project.currency,
                )
            )
    await db.commit()
    _, out = await _rates(db, project)
    return RateCardOut(currency=project.currency, rates=out)


@router.delete("/projects/{project_id}/rate-card", status_code=204)
async def reset_rate_card(project: OwnedProject, db: DB):
    for rc in (
        await db.execute(select(RateCard).where(RateCard.project_id == project.id))
    ).scalars():
        await db.delete(rc)
    await db.commit()


@router.post("/designs/{design_id}/estimate", response_model=EstimateOut, status_code=201)
async def create_estimate(design: OwnedDesign, db: DB):
    """Compute and store a new estimate version."""
    project = await db.get(Project, design.project_id)
    if project is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Project not found")
    if not design.assignments:
        raise HTTPException(status.HTTP_409_CONFLICT, "Assign at least one material first")
    img = await _image(db, project.id)
    regions = await _regions(db, project.id)
    materials = {m.id: material_dict(m) for m in (await db.execute(select(Material))).scalars()}
    rates, _ = await _rates(db, project)
    assignments = [(a.region_id, a.material_id) for a in design.assignments]
    # Rasterises every region at full resolution: keep it off the event loop.
    payload = await asyncio.to_thread(
        estimate_design,
        project,
        regions,
        assignments,
        materials,
        rates,
        img.width or 1000,
        img.height or 1000,
    )
    payload["fingerprint"] = _fingerprint(project, regions, assignments, rates)
    s = payload["scale"]
    project.scale_ft_per_px, project.scale_method, project.scale_confidence = (
        s["ft_per_px"],
        s["method"],
        s["confidence"],
    )
    last = await latest_estimate_row(db, design.id)
    est = Estimate(
        design_id=design.id,
        version=(last.version if last else 0) + 1,
        currency=project.currency,
        grand_total=payload["grand_total"],
        payload=payload,
    )
    db.add(est)
    project.status = "estimated"
    await db.commit()
    await db.refresh(est)
    out = EstimateOut.model_validate(est)
    out.stale = False
    return out


@router.get("/designs/{design_id}/estimate", response_model=EstimateOut)
async def latest_estimate(design: OwnedDesign, db: DB):
    est = await latest_estimate_row(db, design.id)
    if est is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No estimate yet")
    return await _with_stale(db, design, est)
