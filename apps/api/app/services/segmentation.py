"""SegFormer semantic segmentation → taxonomy label map. CPU-only, loaded once per process."""

from __future__ import annotations

import threading
from functools import lru_cache

import numpy as np

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.taxonomy import LABELS, MODEL_LABEL_MAPS

log = get_logger("segmentation")
_lock = threading.Lock()


@lru_cache
def _load():
    import torch
    from transformers import AutoImageProcessor, SegformerForSemanticSegmentation

    name = get_settings().segmentation_model
    log.info("loading_segmentation_model", model=name)
    torch.set_num_threads(max(1, (torch.get_num_threads() or 2)))
    processor = AutoImageProcessor.from_pretrained(name)
    model = SegformerForSemanticSegmentation.from_pretrained(name).eval()
    # ADE class index → taxonomy index (or -1)
    lut = np.full(len(model.config.id2label), -1, dtype=np.int16)
    for i, ade_name in model.config.id2label.items():
        key = ade_name.split(",")[0].strip().lower()
        if key in MODEL_LABEL_MAPS:
            lut[int(i)] = LABELS.index(MODEL_LABEL_MAPS[key])
    return processor, model, lut


def warmup() -> None:
    _load()


def segment(rgb: np.ndarray, max_side: int = 1024) -> tuple[np.ndarray, np.ndarray]:
    """Return (label_map[H,W] int16 with taxonomy indices / -1, confidence[H,W] float32)."""
    import torch
    import torch.nn.functional as F
    from PIL import Image

    processor, model, lut = _load()
    h, w = rgb.shape[:2]
    scale = min(1.0, max_side / max(h, w))
    work = rgb
    if scale < 1.0:
        work = np.asarray(
            Image.fromarray(rgb).resize((int(w * scale), int(h * scale)), Image.BILINEAR)
        )
    inputs = processor(images=Image.fromarray(work), return_tensors="pt")
    with _lock, torch.inference_mode():
        logits = model(**inputs).logits  # [1, C, h/4, w/4]
        logits = F.interpolate(logits, size=(h, w), mode="bilinear", align_corners=False)
        probs = torch.softmax(logits, dim=1)[0]
        conf, ade_idx = probs.max(dim=0)
    label_map = lut[ade_idx.numpy()]
    return label_map.astype(np.int16), conf.numpy().astype(np.float32)
