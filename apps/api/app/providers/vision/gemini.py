"""Gemini 2.5 Flash (free tier) as a second opinion on region labels + floor count.

Never blocks the pipeline: any error / invalid JSON → None and the SegFormer result stands.
"""

from __future__ import annotations

import asyncio
import json

from pydantic import ValidationError

from app.core.config import get_settings
from app.core.logging import get_logger
from app.providers.vision.base import Detection, Refinement
from app.services.taxonomy import LABELS

log = get_logger("gemini")

PROMPT = """You are helping map the exterior of a low-rise residential building for renovation
costing. You get a photo and a JSON list of candidate regions detected by a segmentation model.
Each region has an id, a label, and a bbox as normalised [x0,y0,x1,y1].

Allowed labels: {labels}.

Tasks:
1. relabels: list regions whose label is wrong (e.g. a 'railing' that is actually a 'gate', a 'wall'
   band that is a 'parapet', a 'pillar' that is a drain pipe → drop it by relabeling to "ignore").
2. additions: obvious missing regions (balconies, parapet, gate, pillars) as normalised bboxes.
   Only add things clearly visible. Max 6.
3. floors: number of storeys visible (1-6).
4. door_height_ft: your best estimate of the main door height in feet (usually 7).
Return ONLY JSON:
{{"relabels":[{{"id":"...","label":"..."}}],
 "additions":[{{"label":"...","bbox":[x0,y0,x1,y1],"name":"..."}}],
 "floors":2,"door_height_ft":7,"notes":"..."}}

Regions:
{regions}
"""

DETECT_PROMPT = """You are mapping the exterior of a low-rise residential building for renovation
costing. You get a photo. Detect EVERY visible facade surface and opening — do not stop at a few.

Allowed labels: {labels}.

For each region return a normalised bounding box [x0,y0,x1,y1] with each value in [0,1] (x right,
y down), the label, and a short human name. Detect every wall band, every window and door,
balconies, railings, pillars, parapets, gates and roof edges you can see — typically 8-20 regions
for a normal facade. Ignore people, cars, trees, sky and ground.

Also report:
- floors: number of storeys visible (1-6).
- door_height_ft: your best estimate of the main door height in feet (usually 7).

Return ONLY JSON:
{{"regions":[{{"label":"...","bbox":[x0,y0,x1,y1],"name":"..."}}],
 "floors":2,"door_height_ft":7,"notes":"..."}}
"""


class GeminiRefiner:
    name = "gemini"

    def __init__(self) -> None:
        s = get_settings()
        self.api_key = s.gemini_api_key
        self.model = s.gemini_model

    async def refine(self, jpeg: bytes, regions: list[dict]) -> Refinement | None:
        if not self.api_key:
            return None
        try:
            return await asyncio.wait_for(asyncio.to_thread(self._call, jpeg, regions), timeout=60)
        except Exception as exc:  # noqa: BLE001 - optional tier, must never fail the job
            log.warning("gemini_refine_failed", error=str(exc)[:300])
            return None

    async def detect(self, jpeg: bytes) -> Detection | None:
        """Primary detection: enumerate the whole facade when no local segmenter is available."""
        if not self.api_key:
            return None
        try:
            return await asyncio.wait_for(asyncio.to_thread(self._detect, jpeg), timeout=90)
        except Exception as exc:  # noqa: BLE001 - optional tier, must never fail the job
            log.warning("gemini_detect_failed", error=str(exc)[:300])
            return None

    def _generate(self, jpeg: bytes, prompt: str, max_output_tokens: int) -> str:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.api_key)
        contents: list = [types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"), prompt]
        resp = client.models.generate_content(
            model=self.model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=max_output_tokens,
            ),
        )
        return (resp.text or "").strip()

    def _call(self, jpeg: bytes, regions: list[dict]) -> Refinement | None:
        prompt = PROMPT.format(labels=", ".join(LABELS), regions=json.dumps(regions))
        text = self._generate(jpeg, prompt, max_output_tokens=2048)
        try:
            data = json.loads(text)
            ref = Refinement.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            log.warning("gemini_bad_json", error=str(exc)[:200], text=text[:200])
            return None
        # Drop anything outside our label set except the explicit "ignore" sentinel.
        ref.relabels = [r for r in ref.relabels if r.label in LABELS or r.label == "ignore"]
        ref.additions = [
            a for a in ref.additions if a.label in LABELS and all(0 <= v <= 1 for v in a.bbox)
        ][:6]
        return ref

    def _detect(self, jpeg: bytes) -> Detection | None:
        prompt = DETECT_PROMPT.format(labels=", ".join(LABELS))
        text = self._generate(jpeg, prompt, max_output_tokens=4096)
        try:
            data = json.loads(text)
            det = Detection.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            log.warning("gemini_bad_json", error=str(exc)[:200], text=text[:200])
            return None
        # Keep only regions with a known label and an in-range box; the rest is user-editable.
        det.regions = [
            r for r in det.regions if r.label in LABELS and all(0 <= v <= 1 for v in r.bbox)
        ]
        return det


def get_refiner():
    s = get_settings()
    if s.gemini_api_key:
        return GeminiRefiner()
    from app.providers.vision.base import NoopRefiner

    return NoopRefiner()
