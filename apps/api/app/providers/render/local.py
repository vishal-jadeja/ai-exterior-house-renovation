"""LocalCompositeRenderer — deterministic, dependency-free (OpenCV) material application.

Approach per region:
  1. rasterise polygon → soft mask (feathered edges)
  2. tile the material texture at a real-world scale (texture tile ≈ TILE_FT feet wide)
  3. perspective-warp the tiled texture into the region's dominant quad (approx. facade plane)
  4. multiply by the original luminance (normalised) so shadows, lighting and depth survive
  5. alpha-composite inside the mask; glass/railings keep some of the original for structure
Runs in well under a second on CPU. Photoreal diffusion providers can sit on top of this.
"""

from __future__ import annotations

import asyncio

import cv2
import numpy as np

from app.providers.render.base import RenderRegion, RenderRequest

TILE_FT = 4.0  # one 512px texture tile represents ~4 ft of wall
SEMI_TRANSPARENT = {"railing": 0.72, "gate": 0.85}


def _hex(color: str | None, default=(230, 224, 210)) -> np.ndarray:
    if not color:
        return np.array(default, np.float32)
    c = color.lstrip("#")
    return np.array([int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)], np.float32)


def _quad(poly: np.ndarray) -> np.ndarray:
    """Approximate an arbitrary polygon by its dominant 4-corner quad (facade plane estimate)."""
    cnt = poly.reshape(-1, 1, 2).astype(np.float32)
    peri = cv2.arcLength(cnt, True)
    for f in (0.02, 0.04, 0.08, 0.15):
        approx = cv2.approxPolyDP(cnt, f * peri, True)
        if len(approx) == 4:
            pts = approx.reshape(4, 2)
            return _order(pts)
    x, y, w, h = cv2.boundingRect(cnt)
    return np.array([[x, y], [x + w, y], [x + w, y + h], [x, y + h]], np.float32)


def _order(pts: np.ndarray) -> np.ndarray:
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array(
        [pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], np.float32
    )


def _tiled(texture: np.ndarray, w: int, h: int, px_per_ft: float) -> np.ndarray:
    tile_px = max(24, int(round(TILE_FT * px_per_ft)))
    t = cv2.resize(texture, (tile_px, tile_px), interpolation=cv2.INTER_AREA)
    reps = (h // tile_px + 2, w // tile_px + 2, 1)
    return np.tile(t, reps)[:h, :w]


def _luminance(rgb: np.ndarray) -> np.ndarray:
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    return lab[:, :, 0].astype(np.float32) / 255.0


def render_region(
    canvas: np.ndarray,
    orig: np.ndarray,
    r: RenderRegion,
    px_per_ft: float,
    holes: list[np.ndarray] | None = None,
) -> None:
    h, w = orig.shape[:2]
    poly = np.array(r.polygon, np.float32)
    if len(poly) < 3:
        return
    hard = np.zeros((h, w), np.uint8)
    cv2.fillPoly(hard, [poly.astype(np.int32)], 255)
    if holes and r.label in ("wall", "parapet", "pillar"):
        # Windows, doors, railings are not resurfaced: cut them out of the surface mask.
        cut = np.zeros((h, w), np.uint8)
        cv2.fillPoly(cut, [hp.astype(np.int32) for hp in holes if len(hp) >= 3], 255)
        hard[cut > 0] = 0
    x, y, bw, bh = cv2.boundingRect(poly.astype(np.int32))
    if bw < 2 or bh < 2:
        return
    feather = max(1, int(round(min(bw, bh) * 0.02)) | 1)
    alpha = cv2.GaussianBlur(hard, (feather * 2 + 1, feather * 2 + 1), 0).astype(np.float32) / 255.0
    alpha *= SEMI_TRANSPARENT.get(r.category, 1.0)

    # Base appearance: texture warped onto the region plane, or a flat colour for paint.
    if r.texture is not None and r.category not in ("paint",):
        quad = _quad(poly)
        qx, qy, qw, qh = cv2.boundingRect(quad.astype(np.int32))
        tiled = _tiled(r.texture, max(qw, 2), max(qh, 2), px_per_ft)
        src = np.array([[0, 0], [qw, 0], [qw, qh], [0, qh]], np.float32)
        H_ = cv2.getPerspectiveTransform(src, quad)
        base = cv2.warpPerspective(
            tiled, H_, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT
        ).astype(np.float32)
        if r.category == "texture" and r.color_hex:
            tint = _hex(r.color_hex) / 255.0
            base = base * tint[None, None, :] * 1.15
    else:
        base = np.empty_like(orig, np.float32)
        base[:] = _hex(r.color_hex)

    # Lighting transfer: keep the photo's shading. Blur luminance so fine old texture/detail
    # (brick lines, old paint cracks) does not print through the new material.
    lum = _luminance(orig)
    lum = cv2.GaussianBlur(lum, (0, 0), sigmaX=max(2.0, min(bw, bh) * 0.03))
    m = hard > 0
    if not m.any():
        return
    mean = float(lum[m].mean())
    shade = np.clip(lum / max(mean, 1e-3), 0.6, 1.35)
    shade = 1.0 + 0.8 * (shade - 1.0)  # soften: keep 80% of the photo's shading contrast
    shaded = np.clip(base * shade[..., None], 0, 255)

    a = alpha[..., None]
    canvas[:] = canvas * (1 - a) + shaded * a


class LocalCompositeRenderer:
    name = "local"

    def available(self) -> bool:
        return True

    async def render(self, req: RenderRequest) -> np.ndarray:
        return await asyncio.to_thread(self._render, req)

    def _render(self, req: RenderRequest) -> np.ndarray:
        orig = req.rgb
        canvas = orig.astype(np.float32).copy()
        # Paint large surfaces first so railings/gates composite on top.
        order = {"wall": 0, "parapet": 1, "pillar": 2, "balcony": 3, "railing": 4, "gate": 5}
        holes = [np.array(hp, np.float32) for hp in req.holes]
        for r in sorted(req.regions, key=lambda r: order.get(r.label, 9)):
            render_region(canvas, orig, r, req.px_per_ft, holes)
        req.log.append({"provider": self.name, "status": "ok", "regions": len(req.regions)})
        return np.clip(canvas, 0, 255).astype(np.uint8)
