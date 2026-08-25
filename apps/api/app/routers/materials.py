from fastapi import APIRouter
from sqlalchemy import select

from app.core.deps import DB, CurrentUser
from app.models import Material
from app.providers.storage.s3 import get_storage
from app.schemas.design import MaterialOut

router = APIRouter(prefix="/materials", tags=["materials"])


@router.get("", response_model=list[MaterialOut])
async def list_materials(db: DB, user: CurrentUser):
    rows = (await db.execute(select(Material).order_by(Material.category, Material.name))).scalars()
    storage = get_storage()
    out = []
    for m in rows:
        o = MaterialOut.model_validate(m)
        if m.texture_key:
            o.texture_url = storage.presign(m.texture_key)
        out.append(o)
    return out
