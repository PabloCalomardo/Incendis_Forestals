"""Emergency OSINT publications.

Revision ID: 0004_emergency_osint
Revises: 0003_quality_lineage
"""

from collections.abc import Sequence

import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_emergency_osint"
down_revision: str | None = "0003_quality_lineage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("incidents", "geometry", existing_type=geoalchemy2.types.Geometry(srid=4326), nullable=True)
    op.create_table(
        "emergency_publications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("incidents.id"), nullable=True),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("deduplication_hash", sa.String(length=128), nullable=False, unique=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("authority", sa.String(length=180), nullable=False),
        sa.Column("language", sa.String(length=12), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("original_text", sa.Text(), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("risk_type", sa.String(length=80), nullable=False),
        sa.Column("action_state", sa.String(length=40), nullable=False),
        sa.Column("es_alert_status", sa.String(length=40), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("es_alert_message", sa.Text(), nullable=True),
        sa.Column("locations", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("geometry", geoalchemy2.types.Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True),
        sa.Column("geometry_inference_method", sa.String(length=120), nullable=False),
        sa.Column("spatial_precision", sa.String(length=80), nullable=False),
        sa.Column("evidence_rank", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("review_status", sa.String(length=40), nullable=False),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_emergency_publications_confidence"),
    )
    op.create_index("ix_emergency_publications_incident_time", "emergency_publications", ["incident_id", "published_at"])
    op.create_index("ix_emergency_publications_review", "emergency_publications", ["review_status", "published_at"])
    op.create_index("ix_emergency_publications_event", "emergency_publications", ["event_type", "published_at"])
    op.create_index("ix_emergency_publications_geometry", "emergency_publications", ["geometry"], postgresql_using="gist")


def downgrade() -> None:
    op.drop_index("ix_emergency_publications_geometry", table_name="emergency_publications")
    op.drop_index("ix_emergency_publications_event", table_name="emergency_publications")
    op.drop_index("ix_emergency_publications_review", table_name="emergency_publications")
    op.drop_index("ix_emergency_publications_incident_time", table_name="emergency_publications")
    op.drop_table("emergency_publications")
    op.alter_column("incidents", "geometry", existing_type=geoalchemy2.types.Geometry(srid=4326), nullable=False)
