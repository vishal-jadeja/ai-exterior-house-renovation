from app.services.report_builder import build_report
from tests.helpers import auth, register, synthetic_house
from tests.test_designs import _setup
from tests.test_estimates_api import _design
from tests.test_images import storage  # noqa: F401


def test_build_report_produces_pdf():
    est = {
        "scale": {"ft_per_px": 0.03, "method": "door_reference", "confidence": "medium"},
        "surfaces": [
            {
                "region_id": "w",
                "label": "wall",
                "name": "Wall 1",
                "area_sqft": 400.5,
                "length_ft": None,
                "method": "px",
                "notes": ["openings subtracted"],
            }
        ],
        "lines": [
            {
                "region_id": "w",
                "region_name": "Wall 1",
                "label": "wall",
                "material_name": "Paint",
                "surface": 400.5,
                "surface_unit": "sqft",
                "quantity": 8.4,
                "quantity_unit": "litre",
                "packs": 1,
                "pack_label": "10 L cans",
                "material_rate": 380,
                "labor_rate": 14,
                "material_cost": 3192,
                "labor_cost": 5607,
                "total": 8799,
            }
        ],
        "categories": [
            {"category": "paint", "material_cost": 3192, "labor_cost": 5607, "total": 8799}
        ],
        "material_total": 3192,
        "labor_total": 5607,
        "grand_total": 8799,
        "assumptions": ["main door assumed 7 ft"],
    }
    pdf = build_report(
        project_name="Test house",
        design_name="D1",
        currency="INR",
        original_jpeg=synthetic_house(),
        render_jpeg=synthetic_house(blur=2),
        render_provider="local",
        estimate=est,
        materials=[
            {
                "region_name": "Wall 1",
                "label": "wall",
                "material_name": "Paint",
                "category": "paint",
                "description": "x",
            }
        ],
        owner_email="a@example.com",
    )
    assert pdf.startswith(b"%PDF") and len(pdf) > 20_000


async def test_report_route_and_job(client, storage):  # noqa: F811
    from app.core import db as dbmod
    from app.jobs import report_job
    from app.models import Job

    t, pid, regs = await _setup(client)
    d = await _design(client, t, pid, regs)
    assert (await client.post(f"/designs/{d['id']}/report", headers=auth(t))).status_code == 409
    await client.post(f"/designs/{d['id']}/estimate", headers=auth(t))
    r = await client.post(f"/designs/{d['id']}/report", headers=auth(t))
    assert r.status_code == 202 and r.json()["job_id"]
    async with dbmod.SessionLocal() as s:
        job = await s.get(Job, r.json()["job_id"])
        result = await report_job(s, job)
    assert result["bytes"] > 10_000
    rep = (await client.get(f"/reports/{r.json()['id']}", headers=auth(t))).json()
    assert rep["status"] == "done" and rep["url"].startswith("http://fake/")
    assert next(v for k, v in storage.objects.items() if k.endswith(".pdf")).startswith(b"%PDF")
    other = await register(client, "b@example.com")
    assert (await client.get(f"/reports/{r.json()['id']}", headers=auth(other))).status_code == 404
