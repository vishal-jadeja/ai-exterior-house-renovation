"""Image usability check (spec 5.1). Pure function over pixels; no I/O.

Scores are heuristics tuned for facade photos: sharpness via Laplacian variance, exposure via
mean luminance, contrast via luminance std-dev, plus minimum resolution.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import cv2
import numpy as np

BLUR_HARD_MIN = 40.0  # below → reject
BLUR_SOFT_MIN = 100.0  # below → warn
MIN_SIDE = 640
BRIGHT_MIN, BRIGHT_MAX = 50.0, 215.0
CONTRAST_MIN = 28.0


@dataclass
class QualityResult:
    usable: bool
    score: float
    blur_score: float
    brightness: float
    contrast: float
    guidance: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return self.__dict__.copy()


def assess(image_bgr: np.ndarray, min_side: int = MIN_SIDE) -> QualityResult:
    h, w = image_bgr.shape[:2]
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    # Evaluate blur at a normalised size so the threshold is resolution-independent.
    scale = 1024 / max(h, w)
    g = (
        cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        if scale < 1
        else gray
    )
    blur = float(cv2.Laplacian(g, cv2.CV_64F).var())
    brightness = float(gray.mean())
    contrast = float(gray.std())

    guidance: list[str] = []
    usable = True
    if min(h, w) < min_side:
        usable = False
        guidance.append(
            f"Image is too small ({w}×{h}). Use at least {min_side}px on the short side."
        )
    if blur < BLUR_HARD_MIN:
        usable = False
        guidance.append("Image is very blurry. Hold the camera steady and retake in daylight.")
    elif blur < BLUR_SOFT_MIN:
        guidance.append("Image is slightly soft; a sharper photo will improve region detection.")
    if brightness < BRIGHT_MIN:
        usable = usable and brightness > BRIGHT_MIN * 0.6
        guidance.append("Image is dark. Shoot in daylight so wall textures are visible.")
    elif brightness > BRIGHT_MAX:
        guidance.append("Image is over-exposed. Avoid shooting into direct sun.")
    if contrast < CONTRAST_MIN:
        guidance.append("Low contrast; make sure the whole facade is in frame without haze.")
    if w / h < 0.5 or w / h > 2.5:
        guidance.append("Unusual aspect ratio; frame the full front elevation of the house.")
    if not guidance:
        guidance.append(
            "Looks good. Make sure the full front elevation is visible for best results."
        )

    # Composite 0–100 score for display.
    s_blur = min(blur / 300.0, 1.0)
    s_bright = 1.0 - min(abs(brightness - 128) / 128.0, 1.0)
    s_contrast = min(contrast / 60.0, 1.0)
    s_res = min(min(h, w) / 1200.0, 1.0)
    score = round(100 * (0.45 * s_blur + 0.2 * s_bright + 0.2 * s_contrast + 0.15 * s_res), 1)
    return QualityResult(
        usable, score, round(blur, 1), round(brightness, 1), round(contrast, 1), guidance
    )
