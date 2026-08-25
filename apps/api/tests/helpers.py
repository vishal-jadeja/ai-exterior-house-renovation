from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageFilter


def synthetic_house(w: int = 1024, h: int = 768, blur: float = 0.0) -> bytes:
    """A crude facade: sky, wall, windows, door. Enough texture for a sharp Laplacian."""
    rng = np.random.default_rng(0)
    img = np.full((h, w, 3), 200, np.uint8)
    img[: h // 3] = (235, 206, 135)  # sky (BGR-ish irrelevant here)
    img[h // 3 :] = (180, 170, 160)
    noise = rng.integers(0, 40, (h, w, 1), dtype=np.uint8)
    img = np.clip(img.astype(int) + noise, 0, 255).astype(np.uint8)
    for x in range(100, w - 100, 250):
        img[h // 2 : h // 2 + 120, x : x + 90] = (40, 60, 90)  # windows
    img[h - 220 : h, w // 2 - 60 : w // 2 + 60] = (60, 40, 30)  # door
    pil = Image.fromarray(img)
    if blur:
        pil = pil.filter(ImageFilter.GaussianBlur(blur))
    out = io.BytesIO()
    pil.save(out, format="JPEG", quality=90)
    return out.getvalue()


async def register(client, email="a@example.com", password="password123") -> str:
    r = await client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
