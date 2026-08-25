import json
from pathlib import Path

from app.models import Material
from tests.helpers import auth, register, synthetic_house
from tests.test_images import storage  # noqa: F401

SEED = Path(__file__).resolve().parents[3] / "seed" / "materials.json"


async def _seed(client):
    from app.core import db as dbmod

    async with dbmod.SessionLocal() as s:
        for row in json.loads(SEED.read_text()):
            s.add(Material(**row))
        await s.commit()


async def _setup(client):
    t = await register(client)
    await _seed(client)
    pid = (await client.post("/projects", json={"name": "p"}, headers=auth(t))).json()["id"]
    await client.post(
        f"/projects/{pid}/images",
        files={"file": ("h.jpg", synthetic_house(), "image/jpeg")},
        headers=auth(t),
    )
    regs = (
        await client.put(
            f"/projects/{pid}/regions",
            json={
                "regions": [
                    {"label": "wall", "polygon": [[0, 0], [500, 0], [500, 400], [0, 400]]},
                    {"label": "railing", "polygon": [[50, 50], [250, 50], [250, 80], [50, 80]]},
                ]
            },
            headers=auth(t),
        )
    ).json()
    return t, pid, regs


async def test_materials_listed_with_texture_urls(client, storage):  # noqa: F811
    t = await register(client)
    await _seed(client)
    r = await client.get("/materials", headers=auth(t))
    assert r.status_code == 200 and len(r.json()) == 16
    assert r.json()[0]["texture_url"].startswith("http://fake/textures/")


async def test_design_lifecycle(client, storage):  # noqa: F811
    t, pid, regs = await _setup(client)
    wall, railing = regs
    d1 = (
        await client.post(
            f"/projects/{pid}/designs", json={"name": "Stone + glass"}, headers=auth(t)
        )
    ).json()
    assert d1["is_active"] is True
    d2 = (
        await client.post(f"/projects/{pid}/designs", json={"name": "Paint + SS"}, headers=auth(t))
    ).json()
    assert d2["is_active"] is False

    body = {
        "assignments": [
            {"region_id": wall["id"], "material_id": "cladding-stone-natural"},
            {"region_id": railing["id"], "material_id": "railing-glass"},
        ]
    }
    r = await client.put(f"/designs/{d1['id']}/assignments", json=body, headers=auth(t))
    assert r.status_code == 200 and len(r.json()["assignments"]) == 2

    # material not applicable to label → 422
    bad = {"assignments": [{"region_id": railing["id"], "material_id": "cladding-brick"}]}
    assert (
        await client.put(f"/designs/{d2['id']}/assignments", json=bad, headers=auth(t))
    ).status_code == 422

    # clone carries assignments, activate switches the flag
    c = (await client.post(f"/designs/{d1['id']}/clone", headers=auth(t))).json()
    assert len(c["assignments"]) == 2 and c["name"].endswith("(copy)")
    a = (await client.post(f"/designs/{d2['id']}/activate", headers=auth(t))).json()
    assert a["is_active"] is True
    ds = (await client.get(f"/projects/{pid}/designs", headers=auth(t))).json()
    assert [d["is_active"] for d in ds] == [False, True, False]

    # isolation
    other = await register(client, "b@example.com")
    assert (await client.get(f"/projects/{pid}/designs", headers=auth(other))).status_code == 404
    assert (
        await client.put(f"/designs/{d1['id']}/assignments", json=body, headers=auth(other))
    ).status_code == 404
    assert (await client.delete(f"/designs/{d1['id']}", headers=auth(t))).status_code == 204
