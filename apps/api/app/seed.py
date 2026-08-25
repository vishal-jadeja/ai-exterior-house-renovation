"""Idempotent seed: material catalog from seed/materials.json. Safe to run on every boot."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.models import Material

SEED_FILE = Path(__file__).resolve().parents[3] / "seed" / "materials.json"
log = get_logger("seed")


async def seed_materials() -> int:
    if not SEED_FILE.exists():
        log.warning("seed_file_missing", path=str(SEED_FILE))
        return 0
    rows = json.loads(SEED_FILE.read_text())
    async with SessionLocal() as db:
        existing = {m.id: m for m in (await db.execute(select(Material))).scalars()}
        n = 0
        for row in rows:
            if row["id"] in existing:
                for k, v in row.items():
                    setattr(existing[row["id"]], k, v)
            else:
                db.add(Material(**row))
            n += 1
        await db.commit()
    return n


if __name__ == "__main__":
    configure_logging()
    count = asyncio.run(seed_materials())
    log.info("seeded_materials", count=count)
