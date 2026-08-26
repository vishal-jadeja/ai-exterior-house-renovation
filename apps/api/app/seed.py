"""Idempotent seed: material catalog from seed/materials.json. Safe to run on every boot."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.logging import configure_logging, get_logger
from app.models import Material


def _find_seed_dir() -> Path:
    """`SEED_DIR` env var wins; otherwise walk up from this file looking for `seed/materials.json`.

    A fixed `parents[n]` breaks inside the Docker image, where `app/` sits at `/srv/app` and the
    repo root does not exist.
    """
    if env := os.environ.get("SEED_DIR"):
        return Path(env)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "seed"
        if (candidate / "materials.json").exists():
            return candidate
    return here.parents[min(3, len(here.parents) - 1)] / "seed"


SEED_DIR = _find_seed_dir()
SEED_FILE = SEED_DIR / "materials.json"
TEXTURE_DIR = SEED_DIR / "textures"
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


async def seed_textures() -> int:
    """Upload procedural textures to object storage (idempotent overwrite)."""
    from app.providers.storage.s3 import get_storage

    if not TEXTURE_DIR.exists():
        log.warning("texture_dir_missing", path=str(TEXTURE_DIR))
        return 0
    storage = get_storage()
    storage.ensure_bucket()
    n = 0
    for f in sorted(TEXTURE_DIR.glob("*.jpg")):
        await storage.put(f"textures/{f.name}", f.read_bytes(), "image/jpeg")
        n += 1
    return n


async def main() -> None:
    count = await seed_materials()
    log.info("seeded_materials", count=count)
    try:
        log.info("seeded_textures", count=await seed_textures())
    except Exception as exc:  # noqa: BLE001 - storage may be absent in some dev setups
        log.warning("texture_seed_failed", error=str(exc))


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
