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
