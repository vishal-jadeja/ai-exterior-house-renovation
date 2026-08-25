"""Hosted inpainting providers. Both take the *local composite* as the init image so the
diffusion model refines a plausible material rather than inventing one, and both paste the
result back only inside the mask so the rest of the house is untouched.

Regions are grouped by material so one render costs a handful of calls, not one per window.
"""

from __future__ import annotations

import base64
import io

import cv2
import httpx
import numpy as np
from PIL import Image

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.render.base import ProviderUnavailable, RenderRegion, RenderRequest
from app.providers.render.local import LocalCompositeRenderer

log = get_logger("render.diffusion")
MAX_SIDE = 768


def _groups(regions: list[RenderRegion]) -> dict[str, list[RenderRegion]]:
    out: dict[str, list[RenderRegion]] = {}
    for r in regions:
        out.setdefault(r.material_id, []).append(r)
    return out


def _mask(h: int, w: int, regions: list[RenderRegion], holes: list[np.ndarray]) -> np.ndarray:
    m = np.zeros((h, w), np.uint8)
    cut = np.zeros((h, w), np.uint8)
    if holes:
        cv2.fillPoly(cut, [hp.astype(np.int32) for hp in holes if len(hp) >= 3], 255)
    # Decide per region (not per group) whether openings are protected: one material can be
    # applied to both a wall and a gate, and windows must never be painted over on the wall.
    for r in regions:
        rm = np.zeros((h, w), np.uint8)
        cv2.fillPoly(rm, [np.array(r.polygon, np.int32)], 255)
        if r.label in ("wall", "parapet", "pillar"):
            rm[cut > 0] = 0
        m |= rm
    return m


def _png(arr: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(arr).save(buf, format="PNG")
    return buf.getvalue()


def _decode(data: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))


def _prompt(regions: list[RenderRegion]) -> str:
    r = regions[0]
    color = f", colour {r.color_hex}" if r.color_hex else ""
    return (
        f"{r.prompt_hint or r.material_name}{color}, on the exterior of a residential house, "
        "photorealistic, matching the existing perspective and daylight, high detail"
    )


class _InpaintBase:
    name = "base"
    negative = "blurry, distorted, cartoon, text, watermark, extra windows, changed structure"

    def available(self) -> bool:  # pragma: no cover - overridden
        return False

    async def _inpaint(self, image_png: bytes, mask_png: bytes, prompt: str) -> bytes:
        raise NotImplementedError

    async def render(self, req: RenderRequest) -> np.ndarray:
        if not self.available():
            raise ProviderUnavailable(f"{self.name}: not configured")
        base = await LocalCompositeRenderer().render(req)
        h, w = base.shape[:2]
        scale = min(1.0, MAX_SIDE / max(h, w))
        sw, sh = int(w * scale) // 8 * 8, int(h * scale) // 8 * 8
        small = cv2.resize(base, (sw, sh), interpolation=cv2.INTER_AREA)
        holes = [np.array(hp, np.float32) for hp in req.holes]
        result = base.copy()
        calls = 0
        for material_id, regs in _groups(req.regions).items():
            mask_full = _mask(h, w, regs, holes)
            if mask_full.sum() == 0:
                continue
            mask_small = cv2.resize(mask_full, (sw, sh), interpolation=cv2.INTER_NEAREST)
            out_png = await self._inpaint(_png(small), _png(mask_small), _prompt(regs))
            out = cv2.resize(_decode(out_png), (w, h), interpolation=cv2.INTER_CUBIC)
            soft = cv2.GaussianBlur(mask_full, (0, 0), 3).astype(np.float32)[..., None] / 255.0
            result = (result * (1 - soft) + out * soft).astype(np.uint8)
            calls += 1
            log.info("inpainted", provider=self.name, material=material_id, regions=len(regs))
        req.log.append({"provider": self.name, "status": "ok", "calls": calls})
        return result


class CloudflareInpaintRenderer(_InpaintBase):
    """Cloudflare Workers AI — free tier (10k neurons/day). No card required."""

    name = "cloudflare"
    model = "@cf/runwayml/stable-diffusion-v1-5-inpainting"

    def __init__(self) -> None:
        s = get_settings()
        self.account = s.cf_account_id
        self.token = s.cf_api_token

    def available(self) -> bool:
        return bool(self.account and self.token)

    async def _inpaint(self, image_png: bytes, mask_png: bytes, prompt: str) -> bytes:
        url = f"https://api.cloudflare.com/client/v4/accounts/{self.account}/ai/run/{self.model}"
        payload = {
            "prompt": prompt,
            "negative_prompt": self.negative,
            "image": list(image_png),
            "mask": list(mask_png),
            "num_steps": 20,
            "strength": 0.85,
            "guidance": 7.5,
        }
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                url, json=payload, headers={"Authorization": f"Bearer {self.token}"}
            )
        if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
            raise ProviderUnavailable(f"cloudflare: HTTP {r.status_code} {r.text[:200]}")
        return r.content


class FalInpaintRenderer(_InpaintBase):
    """fal.ai FLUX Fill — best quality; uses signup trial credits."""

    name = "fal"
    endpoint = "https://fal.run/fal-ai/flux-pro/v1/fill"

    def __init__(self) -> None:
        self.key = get_settings().fal_key

    def available(self) -> bool:
        return bool(self.key)

    async def _inpaint(self, image_png: bytes, mask_png: bytes, prompt: str) -> bytes:
        def data_uri(b: bytes) -> str:
            return "data:image/png;base64," + base64.b64encode(b).decode()

        payload = {
            "prompt": prompt,
            "image_url": data_uri(image_png),
            "mask_url": data_uri(mask_png),
            "num_inference_steps": 28,
            "guidance_scale": 30,
            "output_format": "png",
            "safety_tolerance": "2",
        }
        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(
                self.endpoint, json=payload, headers={"Authorization": f"Key {self.key}"}
            )
            if r.status_code != 200:
                raise ProviderUnavailable(f"fal: HTTP {r.status_code} {r.text[:200]}")
            try:
                img_url = r.json()["images"][0]["url"]
            except (KeyError, IndexError, ValueError) as exc:
                raise ProviderUnavailable(f"fal: bad response {r.text[:200]}") from exc
            img = await client.get(img_url)
        if img.status_code != 200:
            raise ProviderUnavailable(f"fal: image download HTTP {img.status_code}")
        return img.content
