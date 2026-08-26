"""estimate (design_id, version) unique

Revision ID: 3f2a9c1d7b44
Revises: 86d1713d4b6a
Create Date: 2026-08-26 12:00:00
"""

from alembic import op

revision = "3f2a9c1d7b44"
down_revision = "86d1713d4b6a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Two concurrent recalculations could both compute `last.version + 1`; the loser must fail
    # loudly (and be retried) rather than leave two rows claiming the same version.
    # batch mode: a no-op wrapper on Postgres, copy-and-move on SQLite (used by the drift test).
    with op.batch_alter_table("estimates") as batch:
        batch.create_unique_constraint("uq_estimates_design_version", ["design_id", "version"])


def downgrade() -> None:
    with op.batch_alter_table("estimates") as batch:
        batch.drop_constraint("uq_estimates_design_version", type_="unique")
