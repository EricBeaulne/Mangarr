"""Bootstrap DB: create tables on empty DB, or add metadata columns for legacy SQLite."""

from typing import Set

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "0001_bootstrap"
down_revision = None
branch_labels = None
depends_on = None


def _column_names(inspector, table: str) -> Set[str]:
    try:
        return {c["name"] for c in inspector.get_columns(table)}
    except sa.exc.NoSuchTableError:
        return set()


def _index_names(inspector, table: str) -> Set[str]:
    return {ix["name"] for ix in inspector.get_indexes(table) if ix.get("name")}


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    if "series" not in inspector.get_table_names():
        from app.database import Base

        Base.metadata.create_all(bind=conn)
        return

    series_cols = _column_names(inspector, "series")
    if "metadata_provider" not in series_cols or "metadata_id" not in series_cols:
        with op.batch_alter_table("series") as batch_op:
            if "metadata_provider" not in series_cols:
                batch_op.add_column(
                    sa.Column("metadata_provider", sa.String(length=32), nullable=True)
                )
            if "metadata_id" not in series_cols:
                batch_op.add_column(sa.Column("metadata_id", sa.String(length=255), nullable=True))

        op.execute(
            sa.text(
                "UPDATE series SET metadata_provider = 'mangadex' "
                "WHERE metadata_provider IS NULL"
            )
        )
        op.execute(
            sa.text(
                "UPDATE series SET metadata_id = mangadex_id "
                "WHERE metadata_id IS NULL AND mangadex_id IS NOT NULL"
            )
        )
        op.execute(
            sa.text(
                "UPDATE series SET metadata_id = CAST(id AS TEXT) "
                "WHERE metadata_id IS NULL OR TRIM(metadata_id) = ''"
            )
        )

        with op.batch_alter_table("series") as batch_op:
            batch_op.alter_column(
                "metadata_provider",
                existing_type=sa.String(length=32),
                nullable=False,
                server_default="mangadex",
            )
            batch_op.alter_column(
                "metadata_id",
                existing_type=sa.String(length=255),
                nullable=False,
            )

    inspector = inspect(conn)
    if "ix_series_provider_metadata" not in _index_names(inspector, "series"):
        op.create_index(
            "ix_series_provider_metadata",
            "series",
            ["metadata_provider", "metadata_id"],
            unique=False,
        )

    if "chapters" in inspector.get_table_names():
        ch_cols = _column_names(inspector, "chapters")
        if "metadata_provider" not in ch_cols:
            with op.batch_alter_table("chapters") as batch_op:
                batch_op.add_column(
                    sa.Column("metadata_provider", sa.String(length=32), nullable=True)
                )
            op.execute(
                sa.text(
                    "UPDATE chapters SET metadata_provider = 'mangadex' "
                    "WHERE metadata_provider IS NULL"
                )
            )
            with op.batch_alter_table("chapters") as batch_op:
                batch_op.alter_column(
                    "metadata_provider",
                    existing_type=sa.String(length=32),
                    nullable=False,
                    server_default="mangadex",
                )


def downgrade() -> None:
    pass
