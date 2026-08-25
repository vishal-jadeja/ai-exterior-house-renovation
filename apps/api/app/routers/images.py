from __future__ import annotations

import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select

from app.core.config import get_settings
from app.core.deps import DB, OwnedProject
from app.core.ratelimit import limiter
from app.models import Image, Region
from app.providers.storage import s3
from app.schemas.project import ImageOut, QualityOut, UploadOut
from app.services import images as imgsvc
from app.services.quality_gate import assess

router = APIRouter(prefix="/projects/{project_id}/images", tags=["images"])


def _with_url(img: Image) -> ImageOut:
    out = ImageOut.model_validate(img)
    out.url = s3.get_storage().presign(img.storage_key)
    return out


@router.get("", response_model=list[ImageOut])
async def list_images(project: OwnedProject, db: DB, kind: str | None = None):
    q = select(Image).where(Image.project_id == project.id).order_by(Image.created_at.desc())
    if kind:
        q = q.where(Image.kind == kind)
    return [_with_url(i) for i in (await db.execute(q)).scalars()]


@router.post("", response_model=UploadOut, status_code=201)
@limiter.limit("20/minute")
async def upload_image(
    request: Request, project: OwnedProject, db: DB, file: Annotated[UploadFile, File()]
):
    settings = get_settings()
    limit = settings.max_upload_bytes
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit + 4096:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image exceeds 10 MB")
    # Read in chunks and stop as soon as the cap is exceeded rather than buffering the body.
    chunks, size = [], 0
    while chunk := await file.read(1024 * 1024):
        size += len(chunk)
        if size > limit:
            raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image exceeds 10 MB")
        chunks.append(chunk)
    data = b"".join(chunks)
    # Decode/resize/re-encode and the blur/brightness analysis are CPU-bound: off the loop.
    jpeg, w, h, bgr = await asyncio.to_thread(imgsvc.sanitize, data)
    quality = await asyncio.to_thread(assess, bgr, settings.min_image_dimension)
    if not quality.usable:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"message": "Image not usable", "quality": quality.as_dict()},
        )
    storage = s3.get_storage()
    # One active source image per project (prototype scope). The previous photo is superseded,
    # never deleted: deleting it would cascade through regions into every design's material
    # assignments. Its regions are deactivated because they are in the old photo's pixel space.
    old = (
        (
            await db.execute(
                select(Image).where(Image.project_id == project.id, Image.kind == "sanitized")
            )
        )
        .scalars()
        .all()
    )
    replaced_regions = 0
    for o in old:
        o.kind = "superseded"
        stale = (
            await db.execute(
                select(Region).where(Region.image_id == o.id, Region.is_active.is_(True))
            )
        ).scalars()
        for r in stale:
            r.is_active = False
            r.version += 1
            replaced_regions += 1
    image_id = str(uuid.uuid4())
    img = Image(
        id=image_id,
        project_id=project.id,
        kind="sanitized",
        # Unique key per upload so a failed commit cannot clobber the previous photo and
        # browsers never serve a cached copy of the old one.
        storage_key=f"projects/{project.id}/source/{image_id}.jpg",
        content_type="image/jpeg",
        width=w,
        height=h,
        quality_score=quality.score,
        meta={"quality": quality.as_dict(), "original_name": file.filename},
    )
    await storage.put(img.storage_key, jpeg, "image/jpeg")
    db.add(img)
    project.status = "uploaded"
    await db.commit()
    await db.refresh(img)
    return UploadOut(
        image=_with_url(img),
        quality=QualityOut(**quality.as_dict()),
        replaced_regions=replaced_regions,
    )


@router.get("/{image_id}", response_model=ImageOut)
async def get_image(image_id: str, project: OwnedProject, db: DB):
    img = await db.get(Image, image_id)
    if img is None or img.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    return _with_url(img)
