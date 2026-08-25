"""Job handlers. Each is `async (db, job) -> dict`. Registered on import by the worker."""

from __future__ import annotations

import asyncio
import io

import numpy as np
from PIL import Image as PILImage
from sqlalchemy import select

from app.core.logging import get_logger
from app.models import Image, Project, Region
from app.providers.storage.s3 import get_storage
from app.providers.vision.gemini import get_refiner
from app.services.jobs import register
from app.services.region_mapper import RegionCandidate, extract_regions, polygon_area
from app.services.taxonomy import HUMAN

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
    jpeg = await get_storage().get(image.storage_key)
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
