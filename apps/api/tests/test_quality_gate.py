import io

import numpy as np
from PIL import Image

from app.services.quality_gate import assess
from tests.helpers import synthetic_house


def _bgr(data: bytes) -> np.ndarray:
    return np.asarray(Image.open(io.BytesIO(data)).convert("RGB"))[:, :, ::-1].copy()


def test_sharp_image_usable():
    q = assess(_bgr(synthetic_house()))
    assert q.usable and q.blur_score > 100


def test_blurry_image_rejected():
    q = assess(_bgr(synthetic_house(blur=12)))
    assert not q.usable
    assert any("blurry" in g.lower() for g in q.guidance)


def test_tiny_image_rejected():
    q = assess(_bgr(synthetic_house(w=300, h=200)))
    assert not q.usable
    assert any("too small" in g for g in q.guidance)
