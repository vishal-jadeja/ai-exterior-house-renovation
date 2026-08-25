import io

import numpy as np
from PIL import Image as PILImage

from app.providers.render.base import ProviderUnavailable, RenderRegion, RenderRequest
from app.providers.render.chain import FallbackChainRenderer
from app.providers.render.local import LocalCompositeRenderer
from tests.helpers import auth, register, synthetic_house
from tests.test_designs import _setup
from tests.test_images import storage  # noqa: F401


def _rgb():
    return np.asarray(PILImage.open(io.BytesIO(synthetic_house())).convert("RGB"))


def _texture():
    return (np.indices((64, 64)).sum(axis=0) % 2 * 255).astype(np.uint8)[..., None].repeat(3, 2)


async def test_local_renderer_changes_only_masked_pixels():
    rgb = _rgb()
    wall = [[100, 300], [700, 300], [700, 700], [100, 700]]
    window = [[200, 400], [300, 400], [300, 500], [200, 500]]
    req = RenderRequest(
        rgb=rgb,
        regions=[
            RenderRegion(
                "r1", "wall", "Wall 1", wall, "stone", "cladding", "Stone", "", _texture(), None
            )
        ],
        px_per_ft=20,
        holes=[window],
    )
    out = await LocalCompositeRenderer().render(req)
    assert out.shape == rgb.shape and out.dtype == np.uint8
    # far outside the wall: untouched
    assert np.array_equal(out[:250, :], rgb[:250, :])
    # inside the wall (away from edges): changed
    assert not np.array_equal(out[450:650, 400:650], rgb[450:650, 400:650])
    # inside the window hole: untouched (openings are preserved)
    assert np.array_equal(out[430:470, 230:270], rgb[430:470, 230:270])
    assert req.log[0]["provider"] == "local"


async def test_paint_uses_colour():
    rgb = _rgb()
    req = RenderRequest(
        rgb=rgb,
        regions=[
            RenderRegion(
                "r1",
                "wall",
                "W",
                [[0, 400], [800, 400], [800, 700], [0, 700]],
                "p",
                "paint",
                "Paint",
                "",
                None,
                "#0000ff",
            )
        ],
        px_per_ft=20,
    )
    out = await LocalCompositeRenderer().render(req)
    patch = out[500:600, 300:500].astype(float).mean(axis=(0, 1))
    assert patch[2] > patch[0] + 60 and patch[2] > patch[1] + 60  # strongly blue


class _Broken:
    name = "broken"

    def available(self):
        return True

    async def render(self, req):
        raise ProviderUnavailable("quota exhausted")


async def test_chain_falls_back_to_local(monkeypatch):
    chain = FallbackChainRenderer(order=["fal", "cloudflare", "local"])  # no keys configured
    chain.providers.insert(0, _Broken())
    req = RenderRequest(rgb=_rgb(), regions=[], px_per_ft=20)
    out, provider = await chain.render(req)
    assert provider == "local" and out.shape == req.rgb.shape
    statuses = {entry["provider"]: entry["status"] for entry in req.log}
    assert statuses["broken"] == "unavailable"
    assert statuses["fal"] == "skipped" and statuses["cloudflare"] == "skipped"
    assert statuses["local"] == "ok"


async def test_render_route_and_job(client, storage):  # noqa: F811
    from app.core import db as dbmod
    from app.jobs import render_job
    from app.models import Job

    t, pid, regs = await _setup(client)
    d = (await client.post(f"/projects/{pid}/designs", json={"name": "d"}, headers=auth(t))).json()
    # no assignments yet → 409
    assert (await client.post(f"/designs/{d['id']}/render", headers=auth(t))).status_code == 409
    await client.put(
        f"/designs/{d['id']}/assignments",
        json={
            "assignments": [
                {
                    "region_id": regs[0]["id"],
                    "material_id": "paint-exterior-emulsion",
                    "color_hex": "#336699",
                }
            ]
        },
        headers=auth(t),
    )
    # textures live in storage; provide one for the paint material's texture_key
    storage.objects["textures/plaster.jpg"] = synthetic_house(w=64, h=64)
    r = await client.post(f"/designs/{d['id']}/render", headers=auth(t))
    assert r.status_code == 202 and r.json()["status"] == "queued" and r.json()["job_id"]
    # run the worker handler inline
    async with dbmod.SessionLocal() as s:
        job = await s.get(Job, r.json()["job_id"])
        result = await render_job(s, job)
    assert result["provider"] == "local"
    rs = (await client.get(f"/designs/{d['id']}/renders", headers=auth(t))).json()
    assert (
        rs[0]["status"] == "done"
        and rs[0]["url"].startswith("http://fake/")
        and rs[0]["provider_used"] == "local"
    )
    # a second design on the same project (regression for the ownership join returning one row
    # per design and MultipleResultsFound-ing on scalar_one_or_none)
    await client.post(f"/designs/{d['id']}/clone", headers=auth(t))
    other = await register(client, "b@example.com")
    assert (await client.get(f"/renders/{rs[0]['id']}", headers=auth(other))).status_code == 404
    assert (await client.get(f"/renders/{rs[0]['id']}", headers=auth(t))).status_code == 200
