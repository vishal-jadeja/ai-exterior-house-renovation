from tests.helpers import auth, register, synthetic_house
from tests.test_images import storage  # noqa: F401  (fixture)


async def _project_with_image(client, token):
    pid = (await client.post("/projects", json={"name": "p"}, headers=auth(token))).json()["id"]
    r = await client.post(
        f"/projects/{pid}/images",
        files={"file": ("h.jpg", synthetic_house(), "image/jpeg")},
        headers=auth(token),
    )
    assert r.status_code == 201
    return pid


async def test_segment_requires_image(client, storage):  # noqa: F811
    t = await register(client)
    pid = (await client.post("/projects", json={"name": "p"}, headers=auth(t))).json()["id"]
    assert (await client.post(f"/projects/{pid}/segment", headers=auth(t))).status_code == 409


async def test_segment_enqueues_idempotently(client, storage):  # noqa: F811
    t = await register(client)
    pid = await _project_with_image(client, t)
    j1 = (await client.post(f"/projects/{pid}/segment", headers=auth(t))).json()
    j2 = (await client.post(f"/projects/{pid}/segment", headers=auth(t))).json()
    assert j1["id"] == j2["id"] and j1["status"] == "queued"
    r = await client.get(f"/jobs/{j1['id']}", headers=auth(t))
    assert r.status_code == 200 and r.json()["type"] == "segment"
    other = await register(client, "b@example.com")
    assert (await client.get(f"/jobs/{j1['id']}", headers=auth(other))).status_code == 404


async def test_put_regions_create_update_deactivate(client, storage):  # noqa: F811
    t = await register(client)
    pid = await _project_with_image(client, t)
    body = {
        "regions": [
            {"label": "wall", "polygon": [[0, 0], [500, 0], [500, 400], [0, 400]]},
            {
                "label": "window",
                "name": "Front window",
                "polygon": [[50, 50], [150, 50], [150, 150], [50, 150]],
            },
        ]
    }
    r = await client.put(f"/projects/{pid}/regions", json=body, headers=auth(t))
    assert r.status_code == 200, r.text
    regs = r.json()
    assert len(regs) == 2 and regs[0]["source"] == "user" and regs[0]["pixel_area"] == 200000
    assert regs[1]["name"] == "Front window" and regs[0]["name"] == "Wall 1"
    # update one, drop the other
    wall = regs[0]
    wall["polygon"] = [[0, 0], [600, 0], [600, 400], [0, 400]]
    r = await client.put(f"/projects/{pid}/regions", json={"regions": [wall]}, headers=auth(t))
    regs = r.json()
    assert len(regs) == 1 and regs[0]["version"] == 2 and regs[0]["pixel_area"] == 240000
    assert len((await client.get(f"/projects/{pid}/regions", headers=auth(t))).json()) == 1
    r = await client.put(
        f"/projects/{pid}/regions",
        json={"regions": [{"label": "spaceship", "polygon": [[0, 0], [1, 0], [1, 1]]}]},
        headers=auth(t),
    )
    assert r.status_code == 422
