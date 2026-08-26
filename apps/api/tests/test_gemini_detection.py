"""Gemini as the primary online detector: JSON parsing/filtering + the segment_job branch.

No network — the genai call is stubbed at `_generate` and the refiner is swapped in `app.jobs`.
"""

from __future__ import annotations

from types import SimpleNamespace

from sqlalchemy import select

from app.core import db as dbmod
from app.core.config import get_settings
from app.models import Region
from app.providers.vision.base import DetectedRegion, Detection
from app.providers.vision.gemini import GeminiRefiner
from tests.helpers import auth, register, synthetic_house
from tests.test_images import storage  # noqa: F401  (fixture)


async def test_detect_parses_and_filters(monkeypatch):
    r = GeminiRefiner()
    r.api_key = "test-key"  # bypass the "no key -> None" short-circuit
    payload = (
        '{"regions": ['
        '{"label": "wall", "bbox": [0, 0, 0.5, 1], "name": "Left wall"},'
        '{"label": "window", "bbox": [0.1, 0.2, 0.2, 0.3], "name": "W1"},'
        '{"label": "spaceship", "bbox": [0, 0, 0.1, 0.1], "name": "nope"},'  # unknown label
        '{"label": "door", "bbox": [0, 0, 1.5, 0.1], "name": "oob"}'  # out-of-range box
        '], "floors": 2, "door_height_ft": 7}'
    )
    monkeypatch.setattr(r, "_generate", lambda jpeg, prompt, max_output_tokens: payload)
    det = await r.detect(b"jpeg-bytes")
    assert det is not None
    labels = [x.label for x in det.regions]
    assert labels == ["wall", "window"]  # spaceship + out-of-range dropped
    assert det.floors == 2


async def test_detect_bad_json_returns_none(monkeypatch):
    r = GeminiRefiner()
    r.api_key = "test-key"
    monkeypatch.setattr(r, "_generate", lambda jpeg, prompt, max_output_tokens: "not json")
    assert await r.detect(b"jpeg-bytes") is None


async def test_detect_without_key_returns_none():
    r = GeminiRefiner()
    r.api_key = None
    assert await r.detect(b"jpeg-bytes") is None


class _FakeGemini:
    name = "gemini"

    async def detect(self, jpeg: bytes) -> Detection:
        return Detection(
            regions=[
                DetectedRegion(label="wall", bbox=[0, 0, 0.5, 1.0], name="Left"),
                DetectedRegion(label="window", bbox=[0.1, 0.2, 0.2, 0.35], name="W"),
            ],
            floors=2,
        )

    async def refine(self, jpeg: bytes, regions: list[dict]):  # never called in this mode
        raise AssertionError("refine must not run when Gemini is the primary detector")


async def _project_with_image(client, token) -> tuple[str, str]:
    pid = (await client.post("/projects", json={"name": "p"}, headers=auth(token))).json()["id"]
    r = await client.post(
        f"/projects/{pid}/images",
        files={"file": ("h.jpg", synthetic_house(), "image/jpeg")},
        headers=auth(token),
    )
    assert r.status_code == 201, r.text
    return pid, r.json()["image"]["id"]


async def test_segment_job_gemini_primary_creates_regions(client, storage, monkeypatch):  # noqa: F811
    import app.jobs as jobs

    t = await register(client)
    pid, image_id = await _project_with_image(client, t)

    monkeypatch.setattr(get_settings(), "detection_provider", "gemini")
    monkeypatch.setattr(jobs, "get_refiner", _FakeGemini)

    job = SimpleNamespace(payload={"project_id": pid, "image_id": image_id})
    async with dbmod.SessionLocal() as db:
        result = await jobs.segment_job(db, job)

    assert result["regions"] == 2 and result["refined"] is True and result["floors"] == 2
    async with dbmod.SessionLocal() as db:
        regs = (
            (
                await db.execute(
                    select(Region).where(Region.project_id == pid, Region.is_active.is_(True))
                )
            )
            .scalars()
            .all()
        )
    assert {r.label for r in regs} == {"wall", "window"}
    assert all(r.source == "gemini" for r in regs)
    assert {r.name for r in regs} == {"Wall 1", "Window 1"}
