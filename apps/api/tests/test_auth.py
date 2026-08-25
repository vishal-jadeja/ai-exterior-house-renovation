from tests.helpers import auth, register


async def test_register_login_me(client):
    token = await register(client)
    r = await client.get("/auth/me", headers=auth(token))
    assert r.status_code == 200 and r.json()["email"] == "a@example.com"
    r = await client.post("/auth/login", json={"email": "a@example.com", "password": "password123"})
    assert r.status_code == 200
    r = await client.post("/auth/login", json={"email": "a@example.com", "password": "wrong-pass"})
    assert r.status_code == 401


async def test_duplicate_email_and_weak_password(client):
    await register(client)
    r = await client.post(
        "/auth/register", json={"email": "a@example.com", "password": "password123"}
    )
    assert r.status_code == 409
    r = await client.post("/auth/register", json={"email": "b@example.com", "password": "short"})
    assert r.status_code == 422


async def test_refresh_and_logout_revokes(client):
    token = await register(client)
    assert "refresh_token" in client.cookies
    r = await client.post("/auth/refresh")
    assert r.status_code == 200 and r.json()["access_token"]
    r = await client.post("/auth/logout", headers=auth(token))
    assert r.status_code == 204
    r = await client.post("/auth/refresh")
    assert r.status_code == 401


async def test_unauthenticated(client):
    assert (await client.get("/projects")).status_code == 401
