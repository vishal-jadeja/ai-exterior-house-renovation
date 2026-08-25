"""Upload validation + sanitisation. Untrusted bytes in, clean JPEG out."""

from __future__ import annotations

import io

import numpy as np
from fastapi import HTTPException, status
from PIL import Image, ImageOps, UnidentifiedImageError

from app.core.config import get_settings

_MAGIC = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"RIFF": "image/webp",
}


def sniff(data: bytes) -> str:
    for magic, mime in _MAGIC.items():
        if data.startswith(magic):
            if mime == "image/webp" and data[8:12] != b"WEBP":
                continue
            return mime
    raise HTTPException(
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only JPEG, PNG or WebP images are accepted"
    )


def sanitize(data: bytes) -> tuple[bytes, int, int, np.ndarray]:
    """Decode, apply EXIF orientation, drop all metadata, clamp size, re-encode as JPEG.

    Returns (jpeg_bytes, width, height, bgr_array).
    """
    s = get_settings()
    if len(data) > s.max_upload_bytes:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Image exceeds 10 MB")
    sniff(data)
    Image.MAX_IMAGE_PIXELS = 40_000_000  # decompression-bomb guard
    try:
        img: Image.Image = Image.open(io.BytesIO(data))
        img = ImageOps.exif_transpose(img) or img
        img = img.convert("RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Could not decode image") from exc
    if max(img.size) > s.max_image_dimension:
        img.thumbnail((s.max_image_dimension, s.max_image_dimension), Image.Resampling.LANCZOS)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=92, optimize=True)  # no exif passed → metadata stripped
    rgb = np.asarray(img)
    bgr = rgb[:, :, ::-1].copy()
    return out.getvalue(), img.width, img.height, bgr
