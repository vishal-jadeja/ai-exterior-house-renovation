"""Job handlers. Each is `async (db, job) -> dict`. Registered on import by the worker."""

from __future__ import annotations

import asyncio
import io

import numpy as np
from PIL import Image as PILImage
from sqlalchemy import select

from app.core.logging import get_logger
from app.models import Design, Estimate, Image, Material, Project, Region, Render, Report, User
from app.providers.render.base import RenderRegion, RenderRequest
from app.providers.render.chain import FallbackChainRenderer
from app.providers.storage import s3
from app.providers.vision.gemini import get_refiner
from app.services.jobs import register
from app.services.region_mapper import RegionCandidate, extract_regions, polygon_area
from app.services.taxonomy import HUMAN, OPENING_LABELS

log = get_logger("jobs")


@register("noop")
async def noop(db, job):
    return {"ok": True}


@register("segment")
async def segment_job(db, job):
    from app.services.segmentation import segment

    project = await db.get(Project, job.payload["project_id"])
    image = await db.get(Image, job.payload["image_id"])
    if project is None or image is None:
        raise RuntimeError("project or image vanished")
    jpeg = await s3.get_storage().get(image.storage_key)
    rgb = np.asarray(PILImage.open(io.BytesIO(jpeg)).convert("RGB"))
    h, w = rgb.shape[:2]

    label_map, conf = await asyncio.to_thread(segment, rgb)
    candidates = extract_regions(label_map, conf)
    log.info("segmented", project_id=project.id, regions=len(candidates))

    # Optional second opinion (Gemini). Never blocks.
    refiner = get_refiner()
    refinement = None
    if refiner.name != "noop":
        small = PILImage.fromarray(rgb)
        small.thumbnail((1024, 1024))
        buf = io.BytesIO()
        small.save(buf, format="JPEG", quality=85)
        payload = [
            {
                "id": str(i),
                "label": c.label,
                "bbox": [
                    round(c.bbox[0] / w, 3),
                    round(c.bbox[1] / h, 3),
                    round((c.bbox[0] + c.bbox[2]) / w, 3),
                    round((c.bbox[1] + c.bbox[3]) / h, 3),
                ],
            }
            for i, c in enumerate(candidates)
        ]
        refinement = await refiner.refine(buf.getvalue(), payload)
    if refinement:
        relabel = {r.id: r.label for r in refinement.relabels}
        kept: list[RegionCandidate] = []
        for i, c in enumerate(candidates):
            new = relabel.get(str(i))
            if new == "ignore":
                continue
            if new and new != c.label:
                c.label, c.source, c.confidence = new, "gemini", max(c.confidence, 0.7)
            kept.append(c)
        for a in refinement.additions:
            x0, y0, x1, y1 = a.bbox[0] * w, a.bbox[1] * h, a.bbox[2] * w, a.bbox[3] * h
            poly = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
            kept.append(
                RegionCandidate(
                    label=a.label,
                    polygon=[[int(x), int(y)] for x, y in poly],
                    pixel_area=polygon_area(poly),
                    bbox=[int(x0), int(y0), int(x1 - x0), int(y1 - y0)],
                    confidence=0.6,
                    name=a.name or "",
                    source="gemini",
                )
            )
        candidates = kept
        if refinement.floors:
            project.floors = refinement.floors
        # re-number names after relabels/additions
        counters: dict[str, int] = {}
        for c in sorted(candidates, key=lambda c: (c.bbox[1] // 50, c.bbox[0])):
            counters[c.label] = counters.get(c.label, 0) + 1
            c.name = f"{HUMAN[c.label]} {counters[c.label]}"

    # Replace previous model/gemini regions; user-drawn regions are preserved.
    old = (
        await db.execute(
            select(Region).where(Region.project_id == project.id, Region.source != "user")
        )
    ).scalars()
    for r in old:
        await db.delete(r)
    for c in candidates:
        db.add(
            Region(
                project_id=project.id,
                image_id=image.id,
                label=c.label,
                name=c.name,
                polygon=c.polygon,
                pixel_area=c.pixel_area,
                bbox=c.bbox,
                confidence=c.confidence,
                source=c.source,
                version=1,
            )
        )
    project.status = "segmented"
    await db.commit()
    return {
        "regions": len(candidates),
        "refined": bool(refinement),
        "floors": project.floors,
        "labels": sorted({c.label for c in candidates}),
    }


def default_px_per_ft(project: Project, width: int) -> float:
    """Texture scale: use the project's estimated scale when known, else assume a ~35 ft facade."""
    if project.scale_ft_per_px:
        return 1.0 / project.scale_ft_per_px
    return width / 35.0


@register("render")
async def render_job(db, job):
    from sqlalchemy.orm import selectinload

    render = await db.get(Render, job.payload["render_id"])
    design = (
        await db.execute(
            select(Design)
            .options(selectinload(Design.assignments))
            .where(Design.id == job.payload["design_id"])
        )
    ).scalar_one_or_none()
    if render is None or design is None:
        raise RuntimeError("render or design vanished")
    render.status = "running"
    await db.commit()
    try:
        project = await db.get(Project, design.project_id)
        image = (
            (
                await db.execute(
                    select(Image)
                    .where(Image.project_id == project.id, Image.kind == "sanitized")
                    .order_by(Image.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        if image is None:
            raise RuntimeError("no source image")
        storage = s3.get_storage()
        rgb = np.asarray(
            PILImage.open(io.BytesIO(await storage.get(image.storage_key))).convert("RGB")
        )
        regions = {
            r.id: r
            for r in (
                await db.execute(
                    select(Region).where(
                        Region.project_id == project.id, Region.is_active.is_(True)
                    )
                )
            ).scalars()
        }
        materials = {m.id: m for m in (await db.execute(select(Material))).scalars()}
        textures: dict[str, np.ndarray] = {}
        rr: list[RenderRegion] = []
        for a in design.assignments:
            r, m = regions.get(a.region_id), materials.get(a.material_id)
            if r is None or m is None:
                continue
            tex = None
            if m.texture_key:
                if m.texture_key not in textures:
                    textures[m.texture_key] = np.asarray(
                        PILImage.open(io.BytesIO(await storage.get(m.texture_key))).convert("RGB")
                    )
                tex = textures[m.texture_key]
            rr.append(
                RenderRegion(
                    region_id=r.id,
                    label=r.label,
                    name=r.name,
                    polygon=r.polygon,
                    material_id=m.id,
                    category=m.category,
                    material_name=m.name,
                    prompt_hint=m.prompt_hint,
                    texture=tex,
                    color_hex=a.color_hex or m.color_hex,
                )
            )
        holes = [r.polygon for r in regions.values() if r.label in OPENING_LABELS]
        req = RenderRequest(
            rgb=rgb, regions=rr, px_per_ft=default_px_per_ft(project, rgb.shape[1]), holes=holes
        )
        out, provider = await FallbackChainRenderer().render(req)
        buf = io.BytesIO()
        PILImage.fromarray(out).save(buf, format="JPEG", quality=90)
        key = f"projects/{project.id}/renders/{render.id}.jpg"
        await storage.put(key, buf.getvalue(), "image/jpeg")
        img = Image(
            project_id=project.id,
            kind="render",
            storage_key=key,
            width=out.shape[1],
            height=out.shape[0],
            meta={"design_id": design.id, "provider": provider},
        )
        db.add(img)
        await db.flush()
        render.image_id = img.id
        render.provider_used = provider
        render.provider_log = req.log
        render.status = "done"
        project.status = "rendered"
        await db.commit()
        return {"render_id": render.id, "provider": provider, "regions": len(rr)}
    except Exception as exc:
        render.status = "failed"
        render.error = str(exc)[:1000]
        await db.commit()
        raise


@register("report")
async def report_job(db, job):
    from sqlalchemy.orm import selectinload

    from app.services.report_builder import build_report

    report = await db.get(Report, job.payload["report_id"])
    design = (
        await db.execute(
            select(Design)
            .options(selectinload(Design.assignments))
            .where(Design.id == job.payload["design_id"])
        )
    ).scalar_one_or_none()
    if report is None or design is None:
        raise RuntimeError("report or design vanished")
    report.status = "running"
    await db.commit()
    try:
        project = await db.get(Project, design.project_id)
        owner = await db.get(User, project.owner_id)
        storage = s3.get_storage()
        source = (
            (
                await db.execute(
                    select(Image)
                    .where(Image.project_id == project.id, Image.kind == "sanitized")
                    .order_by(Image.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        estimate = (
            (
                await db.execute(
                    select(Estimate)
                    .where(Estimate.design_id == design.id)
                    .order_by(Estimate.version.desc())
                )
            )
            .scalars()
            .first()
        )
        if source is None or estimate is None:
            raise RuntimeError("source image or estimate missing")
        render = (
            (
                await db.execute(
                    select(Render)
                    .where(Render.design_id == design.id, Render.status == "done")
                    .order_by(Render.created_at.desc())
                )
            )
            .scalars()
            .first()
        )
        render_jpeg = None
        if render and render.image_id:
            rimg = await db.get(Image, render.image_id)
            if rimg:
                render_jpeg = await storage.get(rimg.storage_key)
        regions = {
            r.id: r
            for r in (
                await db.execute(select(Region).where(Region.project_id == project.id))
            ).scalars()
        }
        materials = {m.id: m for m in (await db.execute(select(Material))).scalars()}
        mats = []
        for a in design.assignments:
            r, m = regions.get(a.region_id), materials.get(a.material_id)
            if r and m:
                mats.append(
                    {
                        "region_name": r.name,
                        "label": r.label,
                        "material_name": m.name,
                        "category": m.category,
                        "description": m.description,
                    }
                )
        pdf = build_report(
            project_name=project.name,
            design_name=design.name,
            currency=estimate.currency,
            original_jpeg=await storage.get(source.storage_key),
            render_jpeg=render_jpeg,
            render_provider=render.provider_used if render else None,
            estimate=estimate.payload,
            materials=mats,
            owner_email=owner.email if owner else "",
        )
        key = f"projects/{project.id}/reports/{report.id}.pdf"
        await storage.put(key, pdf, "application/pdf")
        img = Image(
            project_id=project.id,
            kind="report",
            storage_key=key,
            content_type="application/pdf",
            meta={"design_id": design.id, "estimate_version": estimate.version},
        )
        db.add(img)
        await db.flush()
        report.image_id = img.id
        report.status = "done"
        await db.commit()
        return {"report_id": report.id, "bytes": len(pdf)}
    except Exception as exc:
        report.status = "failed"
        report.error = str(exc)[:1000]
        await db.commit()
        raise
