import pytest

from tests.helpers import auth, register
from tests.test_designs import _setup
from tests.test_images import storage  # noqa: F401


async def _design(client, t, pid, regs):
    d = (await client.post(f"/projects/{pid}/designs", json={"name": "d"}, headers=auth(t))).json()
    await client.put(
        f"/designs/{d['id']}/assignments",
        json={
            "assignments": [
                {"region_id": regs[0]["id"], "material_id": "paint-exterior-emulsion"},
                {"region_id": regs[1]["id"], "material_id": "railing-glass"},
            ]
        },
        headers=auth(t),
    )
    return d


async def test_estimate_versions_and_rate_override(client, storage):  # noqa: F811
    t, pid, regs = await _setup(client)
    d = await _design(client, t, pid, regs)
    assert (await client.get(f"/designs/{d['id']}/estimate", headers=auth(t))).status_code == 404
    e1 = (await client.post(f"/designs/{d['id']}/estimate", headers=auth(t))).json()
    assert e1["version"] == 1 and e1["currency"] == "INR" and e1["grand_total"] > 0
    p = e1["payload"]
    assert p["scale"]["method"] == "default_assumption" and p["scale"]["confidence"] == "low"
    assert {ln["category"] for ln in p["lines"]} == {"paint", "railing"}
    assert p["material_total"] + p["labor_total"] == pytest.approx(p["grand_total"])
    assert any("advisory" in a for a in p["assumptions"])

    # override the paint rate → new estimate is more expensive by exactly the delta
    paint = next(ln for ln in p["lines"] if ln["category"] == "paint")
    rc = (
        await client.put(
            f"/projects/{pid}/rate-card",
            json={
                "rates": [
                    {
                        "material_id": "paint-exterior-emulsion",
                        "material_rate": paint["material_rate"] + 100,
                        "labor_rate": paint["labor_rate"],
                    }
                ]
            },
            headers=auth(t),
        )
    ).json()
    row = next(r for r in rc["rates"] if r["material_id"] == "paint-exterior-emulsion")
    assert row["overridden"] and row["material_rate"] == paint["material_rate"] + 100
    e2 = (await client.post(f"/designs/{d['id']}/estimate", headers=auth(t))).json()
    assert e2["version"] == 2
    assert round(e2["grand_total"] - e1["grand_total"], 2) == round(paint["quantity"] * 100, 2)
    latest = (await client.get(f"/designs/{d['id']}/estimate", headers=auth(t))).json()
    assert latest["version"] == 2

    # reset overrides
    assert (await client.delete(f"/projects/{pid}/rate-card", headers=auth(t))).status_code == 204
    rc = (await client.get(f"/projects/{pid}/rate-card", headers=auth(t))).json()
    assert not any(r["overridden"] for r in rc["rates"])


async def test_measurements_raise_scale_confidence(client, storage):  # noqa: F811
    t, pid, regs = await _setup(client)
    r = await client.patch(
        f"/projects/{pid}/measurements", json={"facade_width_ft": 40, "floors": 2}, headers=auth(t)
    )
    assert r.status_code == 200
    assert r.json()["scale_method"] == "user_measurement" and r.json()["scale_confidence"] == "high"
    assert r.json()["floors"] == 2
    d = await _design(client, t, pid, regs)
    e = (await client.post(f"/designs/{d['id']}/estimate", headers=auth(t))).json()
    assert e["payload"]["scale"]["method"] == "user_measurement"
    # wall polygon is 500px wide = 40 ft → 0.08 ft/px; wall 500x400 px minus railing 200x30
    wall = next(s for s in e["payload"]["surfaces"] if s["label"] == "wall")
    assert abs(wall["area_sqft"] - (500 * 400 - 200 * 30) * 0.08**2) < 5
    other = await register(client, "b@example.com")
    assert (
        await client.post(f"/designs/{d['id']}/estimate", headers=auth(other))
    ).status_code == 404


async def test_estimate_stale_after_rate_change_report_409_while_stale(client, storage):  # noqa: F811
    t, pid, regs = await _setup(client)
    d = await _design(client, t, pid, regs)
    e1 = (await client.post(f"/designs/{d['id']}/estimate", headers=auth(t))).json()
    assert e1["stale"] is False
    got = (await client.get(f"/designs/{d['id']}/estimate", headers=auth(t))).json()
    assert got["stale"] is False

    await client.put(
        f"/projects/{pid}/rate-card",
        json={
            "rates": [
                {
                    "material_id": "paint-exterior-emulsion",
                    "material_rate": 999,
                    "labor_rate": 20,
                }
            ]
        },
        headers=auth(t),
    )
    stale = (await client.get(f"/designs/{d['id']}/estimate", headers=auth(t))).json()
    assert stale["stale"] is True

    r = await client.post(f"/designs/{d['id']}/report", headers=auth(t))
    assert r.status_code == 409

    e2 = (await client.post(f"/designs/{d['id']}/estimate", headers=auth(t))).json()
    assert e2["stale"] is False and e2["version"] == 2


async def test_estimate_stale_after_region_edit(client, storage):  # noqa: F811
    t, pid, regs = await _setup(client)
    d = await _design(client, t, pid, regs)
    e1 = (await client.post(f"/designs/{d['id']}/estimate", headers=auth(t))).json()
    assert e1["stale"] is False

    # Grow the wall polygon: the same ids, a different area → the stored estimate is stale.
    edited = [
        {
            "id": r["id"],
            "label": r["label"],
            "name": r["name"],
            "polygon": [[x * 1.2, y * 1.2] for x, y in r["polygon"]],
        }
        for r in regs
    ]
    r = await client.put(f"/projects/{pid}/regions", json={"regions": edited}, headers=auth(t))
    assert r.status_code == 200, r.text
    got = (await client.get(f"/designs/{d['id']}/estimate", headers=auth(t))).json()
    assert got["stale"] is True
    assert (await client.post(f"/designs/{d['id']}/report", headers=auth(t))).status_code == 409
    e2 = (await client.post(f"/designs/{d['id']}/estimate", headers=auth(t))).json()
    assert e2["version"] == 2 and e2["stale"] is False


async def test_patch_measurements_only_touches_sent_fields(client, storage):  # noqa: F811
    t, pid, regs = await _setup(client)
    r = await client.patch(
        f"/projects/{pid}/measurements", json={"facade_width_ft": 40}, headers=auth(t)
    )
    assert r.status_code == 200 and r.json()["facade_width_ft"] == 40

    r = await client.patch(f"/projects/{pid}/measurements", json={"floors": 2}, headers=auth(t))
    assert r.status_code == 200
    assert r.json()["floors"] == 2 and r.json()["facade_width_ft"] == 40
