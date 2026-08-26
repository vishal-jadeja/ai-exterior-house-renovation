"""The migrations and the ORM models must describe the same schema.

Tests build tables from `Base.metadata`; Postgres is provisioned through alembic. Any drift means
the code is tested against a schema production does not have.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine

from app.models import Base

VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"


def _ordered_revisions():
    mods = []
    for p in sorted(VERSIONS.glob("*.py")):
        spec = importlib.util.spec_from_file_location(p.stem, p)
        assert spec and spec.loader
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mods.append(mod)
    by_down = {m.down_revision: m for m in mods}
    chain, cur = [], None
    while cur in by_down:
        m = by_down[cur]
        chain.append(m)
        cur = m.revision
    assert len(chain) == len(mods), "migration chain is not linear"
    return chain


def test_migrations_match_models():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            for m in _ordered_revisions():
                m.upgrade()
        diff = compare_metadata(
            MigrationContext.configure(conn, opts={"compare_server_default": True}),
            Base.metadata,
        )
    # `func.now()` (models) and `text("now()")` (migrations) are the same default rendered
    # differently; every other server-default difference is real drift.
    flat = [x for d in diff for x in (d if isinstance(d, list) else [d])]
    diff = [
        d for d in flat if not (d[0] == "modify_default" and d[3] in ("created_at", "updated_at"))
    ]
    assert diff == [], "\n".join(str(d) for d in diff)
