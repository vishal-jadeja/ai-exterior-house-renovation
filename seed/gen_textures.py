"""Generate tileable procedural material textures (no licensing worries) into seed/textures/.

Run: python seed/gen_textures.py   (needs numpy + Pillow)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

OUT = Path(__file__).resolve().parent / "textures"
S = 512
rng = np.random.default_rng(42)


def noise(scale: float = 1.0, octaves: int = 4) -> np.ndarray:
    acc = np.zeros((S, S))
    amp = 1.0
    for o in range(octaves):
        n = 2 ** (o + 2)
        base = rng.random((n, n))
        img = Image.fromarray((base * 255).astype(np.uint8)).resize((S, S), Image.BICUBIC)
        acc += amp * (np.asarray(img) / 255.0)
        amp *= 0.5
    acc = (acc - acc.min()) / (acc.max() - acc.min())
    return acc**scale


def save(name: str, arr: np.ndarray) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(OUT / name, quality=90)


def flat(color, grain=0.06, scale=1.0):
    n = noise(scale)
    c = np.array(color, float)
    return c[None, None, :] * (1 - grain + grain * 2 * n[..., None])


def bricks(brick=(178, 84, 62), mortar=(205, 198, 185), bw=64, bh=28, gap=4):
    img = Image.new("RGB", (S, S), mortar)
    d = ImageDraw.Draw(img)
    row = 0
    for y in range(0, S, bh):
        off = (bw // 2) if row % 2 else 0
        for x in range(-bw, S + bw, bw):
            jitter = rng.integers(-12, 12, 3)
            col = tuple(int(np.clip(c + j, 0, 255)) for c, j in zip(brick, jitter))
            d.rectangle([x + off + gap // 2, y + gap // 2, x + off + bw - gap // 2, y + bh - gap // 2], fill=col)
        row += 1
    a = np.asarray(img).astype(float)
    return a * (0.9 + 0.2 * noise(1.5)[..., None])


def stone(cols=((168, 158, 142), (192, 182, 165), (140, 132, 122), (205, 196, 180)), n=70):
    pts = rng.random((n, 2)) * S
    yy, xx = np.mgrid[0:S, 0:S]
    # toroidal Voronoi for tileability
    best = np.full((S, S), np.inf)
    idx = np.zeros((S, S), int)
    for i, (px, py) in enumerate(pts):
        dx = np.minimum(np.abs(xx - px), S - np.abs(xx - px))
        dy = np.minimum(np.abs(yy - py), S - np.abs(yy - py))
        d = dx * dx + dy * dy
        m = d < best
        best[m] = d[m]
        idx[m] = i
    palette = np.array([cols[i % len(cols)] for i in range(n)], float)
    palette += rng.integers(-18, 18, (n, 1))  # luminance jitter only, keep hue
    img = palette[idx]
    edge = np.abs(np.gradient(idx.astype(float))[0]) + np.abs(np.gradient(idx.astype(float))[1])
    img[edge > 0] = (70, 66, 62)
    a = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.6))
    return np.asarray(a).astype(float) * (0.85 + 0.3 * noise(1.2)[..., None])


def ledgestone(cols=((140, 132, 120), (110, 105, 98), (165, 155, 140))):
    img = Image.new("RGB", (S, S), (60, 58, 55))
    d = ImageDraw.Draw(img)
    y = 0
    while y < S:
        h = int(rng.integers(14, 30))
        x = int(rng.integers(-40, 0))
        while x < S:
            w = int(rng.integers(40, 120))
            c = cols[int(rng.integers(0, len(cols)))]
            c = tuple(int(np.clip(v + rng.integers(-12, 12), 0, 255)) for v in c)
            d.rectangle([x + 1, y + 1, x + w - 2, y + h - 2], fill=c)
            x += w
        y += h
    return np.asarray(img).astype(float) * (0.85 + 0.3 * noise(1.3)[..., None])


def tiles(size, base=(214, 205, 188), grout=(150, 145, 135), gap=3):
    img = Image.new("RGB", (S, S), grout)
    d = ImageDraw.Draw(img)
    for y in range(0, S, size):
        for x in range(0, S, size):
            j = rng.integers(-8, 8, 3)
            d.rectangle([x + gap, y + gap, x + size - gap, y + size - gap], fill=tuple(int(b + k) for b, k in zip(base, j)))
    return np.asarray(img).astype(float) * (0.92 + 0.16 * noise(2)[..., None])


def louvers(a=(96, 64, 40), b=(130, 90, 58), w=18, gap=6):
    img = np.zeros((S, S, 3))
    for x in range(0, S, w + gap):
        img[:, x : x + w] = a
        img[:, x + w // 3 : x + w // 3 + 3] = b
    return img * (0.9 + 0.2 * noise(1.5)[..., None])


def panels(color=(138, 143, 148), seam=64, seam_col=(70, 72, 75)):
    img = flat(color, 0.03)
    img[::seam, :] = seam_col
    img[:, ::seam] = seam_col
    return img


def bars(bg=(200, 205, 210), bar=(45, 45, 45), w=6, gap=26, horizontal=False):
    img = np.full((S, S, 3), bg, float)
    for p in range(0, S, gap):
        if horizontal:
            img[p : p + w, :] = bar
        else:
            img[:, p : p + w] = bar
    return img


def glass():
    img = flat((175, 205, 215), 0.08, 1.5)
    img[::48, :] = (230, 235, 240)
    return img


if __name__ == "__main__":
    save("plaster.jpg", flat((232, 226, 212), 0.05))
    save("rustic.jpg", flat((217, 201, 168), 0.35, 0.8))
    save("spray.jpg", flat((207, 211, 214), 0.25, 2.0))
    save("stone.jpg", stone())
    save("ledgestone.jpg", ledgestone())
    save("brick.jpg", bricks())
    save("tile-large.jpg", tiles(128))
    save("tile-small.jpg", tiles(64, base=(228, 224, 210)))
    save("glass.jpg", glass())
    save("steel.jpg", bars(bg=(190, 196, 200), bar=(120, 125, 130), w=8, gap=40, horizontal=True))
    save("ms.jpg", bars())
    save("wood-panel.jpg", louvers(a=(120, 82, 50), b=(150, 105, 65), w=64, gap=2))
    save("acp.jpg", panels())
    save("louver.jpg", louvers())
    print("textures written to", OUT)
