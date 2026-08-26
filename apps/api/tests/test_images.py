from __future__ import annotations

import pytest

from app.providers.storage import s3
from tests.helpers import auth, register, synthetic_house


class FakeStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    async def put(self, key, data, content_type):
        self.objects[key] = data

    async def get(self, key):
        return self.objects[key]

    async def delete(self, key):
        self.objects.pop(key, None)

    def presign(self, key, filename=None):
        return f"http://fake/{key}"


@pytest.fixture
def storage(monkeypatch):
    fake = FakeStorage()
    monkeypatch.setattr(
        s3, "get_storage", lambda: fake
    )  # every caller goes through s3.get_storage()
    return fake


async def _project(client, token):
    r = await client.post("/projects", json={"name": "p"}, headers=auth(token))
    return r.json()["id"]


async def test_upload_good_image(client, storage):
    t = await register(client)
    pid = await _project(client, t)
    r = await client.post(
        f"/projects/{pid}/images",
        files={"file": ("house.jpg", synthetic_house(), "image/jpeg")},
        headers=auth(t),
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["quality"]["usable"] and body["image"]["url"].startswith("http://fake/")
    assert body["image"]["width"] == 1024
    assert len(storage.objects) == 1
    # stored file is a re-encoded JPEG (metadata stripped)
    assert next(iter(storage.objects.values())).startswith(b"\xff\xd8\xff")


async def test_upload_blurry_rejected_with_guidance(client, storage):
    t = await register(client)
    pid = await _project(client, t)
    r = await client.post(
        f"/projects/{pid}/images",
        files={"file": ("house.jpg", synthetic_house(blur=12), "image/jpeg")},
        headers=auth(t),
    )
    assert r.status_code == 422
    assert r.json()["detail"]["quality"]["guidance"]


async def test_upload_rejects_non_image(client, storage):
    t = await register(client)
    pid = await _project(client, t)
    r = await client.post(
        f"/projects/{pid}/images",
        files={"file": ("x.jpg", b"<html>not an image</html>", "image/jpeg")},
        headers=auth(t),
    )
    assert r.status_code == 415


async def test_upload_oversize_rejected(client, storage):
    t = await register(client)
    pid = await _project(client, t)
    r = await client.post(
        f"/projects/{pid}/images",
        files={"file": ("huge.jpg", b"\xff" * (11 * 1024 * 1024), "image/jpeg")},
        headers=auth(t),
    )
    assert r.status_code == 413


async def test_reupload_deactivates_regions_and_keeps_assignments(client, storage):
    from tests.test_designs import _seed

    t = await register(client)
    await _seed(client)
    pid = await _project(client, t)
    await client.post(
        f"/projects/{pid}/images",
        files={"file": ("house.jpg", synthetic_house(), "image/jpeg")},
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
    d = (await client.post(f"/projects/{pid}/designs", json={"name": "d"}, headers=auth(t))).json()
    d = (
        await client.put(
            f"/designs/{d['id']}/assignments",
            json={
                "assignments": [
                    {"region_id": regs[0]["id"], "material_id": "paint-exterior-emulsion"}
                ]
            },
            headers=auth(t),
        )
    ).json()
    assert len(d["assignments"]) == 1

    r = await client.post(
        f"/projects/{pid}/images",
        files={"file": ("house2.jpg", synthetic_house(), "image/jpeg")},
        headers=auth(t),
    )
    assert r.status_code == 201
    assert r.json()["replaced_regions"] == len(regs)

    # the old regions are deactivated, not deleted or cascade-removed
    assert (await client.get(f"/projects/{pid}/regions", headers=auth(t))).json() == []
    d2 = (await client.get(f"/projects/{pid}/designs", headers=auth(t))).json()[0]
    assert len(d2["assignments"]) == 1

    # ...but nothing downstream may pretend those orphaned assignments still mean something:
    # an estimate would be ₹0 and a render would hand back the untouched photo as "redesigned".
    for path in (f"/designs/{d['id']}/estimate", f"/designs/{d['id']}/render"):
        r = await client.post(path, headers=auth(t))
        assert r.status_code == 409, (path, r.text)
        assert "regions" in r.json()["detail"].lower()
    r = await client.post(f"/designs/{d['id']}/report", headers=auth(t))
    assert r.status_code == 409


async def test_upload_foreign_project_404(client, storage):
    a = await register(client, "a@example.com")
    b = await register(client, "b@example.com")
    pid = await _project(client, a)
    r = await client.post(
        f"/projects/{pid}/images",
        files={"file": ("house.jpg", synthetic_house(), "image/jpeg")},
        headers=auth(b),
    )
    assert r.status_code == 404
