"""quality lineage

Revision ID: 0003_quality_lineage
Revises: 0002_domain_lineage_model
Create Date: 2026-07-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_quality_lineage"
down_revision: str | None = "0002_domain_lineage_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def id_column() -> sa.Column[str]:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)


def timestamps() -> list[sa.Column[str]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "confidence_assessments",
        id_column(),
        sa.Column("resource_type", sa.String(length=120), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("algorithm_version", sa.String(length=80), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=False),
        sa.Column("factors", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("penalties", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        *timestamps(),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_confidence_assessments_confidence"),
    )
    op.create_index(
        "ix_confidence_assessments_resource",
        "confidence_assessments",
        ["resource_type", "resource_id"],
    )
    op.create_index("ix_confidence_assessments_calculated_at", "confidence_assessments", ["calculated_at"])

    op.create_table(
        "data_conflicts",
        id_column(),
        sa.Column("conflict_type", sa.String(length=120), nullable=False),
        sa.Column("resource_type", sa.String(length=120), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("conflicting_resource_type", sa.String(length=120), nullable=False),
        sa.Column("conflicting_resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        *timestamps(),
    )
    op.create_index("ix_data_conflicts_resource", "data_conflicts", ["resource_type", "resource_id"])
    op.create_index(
        "ix_data_conflicts_conflicting_resource",
        "data_conflicts",
        ["conflicting_resource_type", "conflicting_resource_id"],
    )
    op.create_index("ix_data_conflicts_type", "data_conflicts", ["conflict_type"])

    op.create_table(
        "observation_links",
        id_column(),
        sa.Column("resource_type", sa.String(length=120), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("related_resource_type", sa.String(length=120), nullable=False),
        sa.Column("related_resource_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("relation_kind", sa.String(length=120), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        *timestamps(),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_observation_links_confidence"),
    )
    op.create_index("ix_observation_links_resource", "observation_links", ["resource_type", "resource_id"])
    op.create_index(
        "ix_observation_links_related_resource",
        "observation_links",
        ["related_resource_type", "related_resource_id"],
    )
    op.create_index("ix_observation_links_kind", "observation_links", ["relation_kind"])


def downgrade() -> None:
    op.drop_index("ix_observation_links_kind", table_name="observation_links")
    op.drop_index("ix_observation_links_related_resource", table_name="observation_links")
    op.drop_index("ix_observation_links_resource", table_name="observation_links")
    op.drop_table("observation_links")

    op.drop_index("ix_data_conflicts_type", table_name="data_conflicts")
    op.drop_index("ix_data_conflicts_conflicting_resource", table_name="data_conflicts")
    op.drop_index("ix_data_conflicts_resource", table_name="data_conflicts")
    op.drop_table("data_conflicts")

    op.drop_index("ix_confidence_assessments_calculated_at", table_name="confidence_assessments")
    op.drop_index("ix_confidence_assessments_resource", table_name="confidence_assessments")
    op.drop_table("confidence_assessments")
