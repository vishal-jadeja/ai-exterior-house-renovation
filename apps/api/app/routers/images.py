from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from sqlalchemy import select

from app.core.deps import DB, OwnedProject
from app.core.ratelimit import limiter
from app.models import Image
from app.providers.storage.s3 import get_storage
from app.schemas.project import ImageOut, QualityOut, UploadOut
from app.services import images as imgsvc
from app.services.quality_gate import assess

router = APIRouter(prefix="/projects/{project_id}/images", tags=["images"])


def _with_url(img: Image) -> ImageOut:
    out = ImageOut.model_validate(img)
    out.url = get_storage().presign(img.storage_key)
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
    data = await file.read()
    jpeg, w, h, bgr = imgsvc.sanitize(data)
    quality = assess(bgr)
    if not quality.usable:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            {"message": "Image not usable", "quality": quality.as_dict()},
        )
    storage = get_storage()
    # Replace any previous facade photo: one active source image per project (prototype scope).
    old = (
        (
            await db.execute(
                select(Image).where(Image.project_id == project.id, Image.kind == "sanitized")
            )
        )
        .scalars()
        .all()
    )
    for o in old:
        await db.delete(o)
    img = Image(
        project_id=project.id,
        kind="sanitized",
        storage_key=f"projects/{project.id}/source/{project.id}.jpg",
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
    return UploadOut(image=_with_url(img), quality=QualityOut(**quality.as_dict()))


@router.get("/{image_id}", response_model=ImageOut)
async def get_image(image_id: str, project: OwnedProject, db: DB):
    img = await db.get(Image, image_id)
    if img is None or img.project_id != project.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Image not found")
    return _with_url(img)
