"""Add anilist_id, anilist_volumes, anilist_chapters to series table."""

from typing import Set

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0002_anilist_columns"
down_revision = "0001_bootstrap"
branch_labels = None
depends_on = None


def _column_names(inspector, table: str) -> Set[str]:
    try:
        return {c["name"] for c in inspector.get_columns(table)}
    except sa.exc.NoSuchTableError:
        return set()


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing = _column_names(inspector, "series")

    with op.batch_alter_table("series") as batch_op:
        if "anilist_id" not in existing:
            batch_op.add_column(sa.Column("anilist_id", sa.Integer(), nullable=True))
        if "anilist_volumes" not in existing:
            batch_op.add_column(sa.Column("anilist_volumes", sa.Integer(), nullable=True))
        if "anilist_chapters" not in existing:
            batch_op.add_column(sa.Column("anilist_chapters", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("series") as batch_op:
        batch_op.drop_column("anilist_chapters")
        batch_op.drop_column("anilist_volumes")
        batch_op.drop_column("anilist_id")
