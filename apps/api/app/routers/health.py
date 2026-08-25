from fastapi import APIRouter
from sqlalchemy import text

from app.core.deps import DB

router = APIRouter(tags=["health"])


@router.get("/health")
async def health(db: DB):
    await db.execute(text("SELECT 1"))
    return {"status": "ok"}
