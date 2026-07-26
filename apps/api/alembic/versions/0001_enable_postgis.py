"""enable postgis and bootstrap readiness table

Revision ID: 0001_enable_postgis
Revises:
Create Date: 2026-07-25 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_enable_postgis"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "schema_migrations_readiness",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("component", sa.String(length=64), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        "INSERT INTO schema_migrations_readiness (component) "
        "VALUES ('postgis') ON CONFLICT (component) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("schema_migrations_readiness")
    op.execute("DROP EXTENSION IF EXISTS postgis")
