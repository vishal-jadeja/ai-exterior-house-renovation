from tests.helpers import auth, register


async def test_project_crud_and_isolation(client):
    a = await register(client, "a@example.com")
    b = await register(client, "b@example.com")
    r = await client.post(
        "/projects", json={"name": "My house", "currency": "inr"}, headers=auth(a)
    )
    assert r.status_code == 201
    pid = r.json()["id"]
    assert r.json()["currency"] == "INR"
    assert len((await client.get("/projects", headers=auth(a))).json()) == 1
    assert (await client.get("/projects", headers=auth(b))).json() == []
    # foreign project → 404, never 403 (no ID enumeration)
    assert (await client.get(f"/projects/{pid}", headers=auth(b))).status_code == 404
    assert (
        await client.patch(f"/projects/{pid}", json={"name": "x"}, headers=auth(b))
    ).status_code == 404
    r = await client.patch(f"/projects/{pid}", json={"name": "Renamed"}, headers=auth(a))
    assert r.json()["name"] == "Renamed"
    assert (await client.delete(f"/projects/{pid}", headers=auth(a))).status_code == 204
    assert (await client.get(f"/projects/{pid}", headers=auth(a))).status_code == 404
