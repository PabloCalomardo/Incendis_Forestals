"""domain lineage model

Revision ID: 0002_domain_lineage_model
Revises: 0001_enable_postgis
Create Date: 2026-07-26 00:00:00.000000
"""

from collections.abc import Sequence

from alembic import op
import geoalchemy2
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_domain_lineage_model"
down_revision: str | None = "0001_enable_postgis"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

provenance_type = postgresql.ENUM(
    "official", "observed", "estimated", "unverified", name="provenance_type", create_type=False
)
data_source_type = postgresql.ENUM(
    "official", "observed", "estimated", "unverified", name="data_source_type", create_type=False
)
verification_status = postgresql.ENUM(
    "verified", "partial", "pending", "rejected", name="verification_status", create_type=False
)
incident_status = postgresql.ENUM(
    "reported",
    "active",
    "stabilized",
    "controlled",
    "extinguished",
    "archived",
    name="incident_status",
    create_type=False,
)
ingestion_run_status = postgresql.ENUM(
    "started",
    "completed",
    "failed",
    "partial",
    "cancelled",
    name="ingestion_run_status",
    create_type=False,
)
zone_kind = postgresql.ENUM("evacuation", "restriction", name="zone_kind", create_type=False)
road_incident_kind = postgresql.ENUM(
    "official_closure",
    "inside_perimeter",
    "smoke_probable",
    "reduced_visibility",
    "insufficient_data",
    name="road_incident_kind",
    create_type=False,
)
user_role = postgresql.ENUM(
    "firefighter", "analyst", "incident_commander", "administrator", name="user_role", create_type=False
)


def id_column() -> sa.Column[str]:
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True)


def timestamps() -> list[sa.Column[str]]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def lineage_columns(nullable_source: bool = True) -> list[sa.Column[str]]:
    return [
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("data_sources.id"), nullable=nullable_source),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("provenance", provenance_type, nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verification_status", verification_status, nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("original_metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("deduplication_hash", sa.String(length=128), nullable=True),
    ]


def spatial_column(name: str = "geometry", geometry_type: str = "GEOMETRY") -> sa.Column[str]:
    return sa.Column(name, geoalchemy2.Geometry(geometry_type=geometry_type, srid=4326), nullable=False)


def create_temporal_indexes(table: str) -> None:
    for column in ("observed_at", "published_at", "received_at", "expires_at"):
        op.create_index(f"ix_{table}_{column}", table, [column])


def create_lineage_indexes(table: str) -> None:
    op.create_index(f"ix_{table}_source_external", table, ["source_id", "external_id"])
    op.create_index(f"ix_{table}_deduplication_hash", table, ["deduplication_hash"])
    op.create_index(f"ix_{table}_provenance", table, ["provenance"])
    create_temporal_indexes(table)


def upgrade() -> None:
    for enum in (
        provenance_type,
        data_source_type,
        verification_status,
        incident_status,
        ingestion_run_status,
        zone_kind,
        road_incident_kind,
        user_role,
    ):
        enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "data_sources",
        id_column(),
        *timestamps(),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("source_type", data_source_type, nullable=False),
        sa.Column("authority", sa.String(length=160), nullable=True),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("license_name", sa.String(length=160), nullable=True),
        sa.Column("attribution", sa.Text(), nullable=True),
        sa.Column("update_frequency", sa.String(length=120), nullable=True),
        sa.Column("expected_delay_seconds", sa.Integer(), nullable=True),
        sa.Column("reliability_score", sa.Float(), nullable=True),
        sa.Column("source_metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.CheckConstraint("reliability_score IS NULL OR (reliability_score >= 0 AND reliability_score <= 1)", name="ck_data_sources_reliability"),
        sa.UniqueConstraint("name", name="uq_data_sources_name"),
    )

    op.create_table(
        "roles",
        id_column(),
        *timestamps(),
        sa.Column("name", user_role, nullable=False),
        sa.Column("permissions", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )
    op.create_table(
        "users",
        id_column(),
        *timestamps(),
        sa.Column("external_subject", sa.String(length=240), nullable=False),
        sa.Column("email", sa.String(length=240), nullable=True),
        sa.Column("display_name", sa.String(length=240), nullable=True),
        sa.Column("role_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("roles.id"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.UniqueConstraint("external_subject", name="uq_users_external_subject"),
    )

    op.create_table(
        "data_ingestion_runs",
        id_column(),
        *timestamps(),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("data_sources.id"), nullable=False),
        sa.Column("connector_name", sa.String(length=120), nullable=False),
        sa.Column("status", ingestion_run_status, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("received_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("discarded_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("duplicate_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("persisted_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("raw_object_uri", sa.Text(), nullable=True),
        sa.Column("error_summary", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.create_index("ix_data_ingestion_runs_source_started", "data_ingestion_runs", ["source_id", "started_at"])

    op.create_table(
        "incidents",
        id_column(),
        *timestamps(),
        *lineage_columns(),
        spatial_column(),
        sa.Column("original_crs", sa.String(length=64), server_default="EPSG:4326", nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("status", incident_status, nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_incidents_confidence"),
    )
    op.create_index("ix_incidents_geometry", "incidents", ["geometry"], postgresql_using="gist")
    op.create_index("ix_incidents_status", "incidents", ["status"])
    create_lineage_indexes("incidents")

    op.create_table(
        "incident_versions",
        id_column(),
        *timestamps(),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("incidents.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", incident_status, nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("changed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.UniqueConstraint("incident_id", "version", name="uq_incident_versions_incident_version"),
    )

    op.create_table(
        "model_executions",
        id_column(),
        *timestamps(),
        sa.Column("model_name", sa.String(length=120), nullable=False),
        sa.Column("model_version", sa.String(length=80), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("input_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_hash", sa.String(length=128), nullable=False),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("status", sa.String(length=60), nullable=False),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.create_index("ix_model_executions_name_version", "model_executions", ["model_name", "model_version"])
    op.create_index("ix_model_executions_input_hash", "model_executions", ["input_hash"])

    _create_domain_tables()


def _create_domain_tables() -> None:
    table_specs = [
        ("fire_detections", "POINT"),
        ("fire_perimeters", "GEOMETRY"),
        ("evacuation_zones", "GEOMETRY"),
        ("restriction_zones", "GEOMETRY"),
        ("road_segments", "LINESTRING"),
        ("weather_observations", "POINT"),
        ("weather_forecasts", "POINT"),
        ("smoke_forecasts", "GEOMETRY"),
        ("risk_forecasts", "GEOMETRY"),
    ]

    op.create_table(
        "fire_detections",
        id_column(),
        *timestamps(),
        *lineage_columns(),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("incidents.id"), nullable=True),
        spatial_column(geometry_type="POINT"),
        sa.Column("original_crs", sa.String(length=64), server_default="EPSG:4326", nullable=False),
        sa.Column("sensor", sa.String(length=80), nullable=True),
        sa.Column("satellite", sa.String(length=80), nullable=True),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("frp_mw", sa.Float(), nullable=True),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="ck_fire_detections_confidence"),
    )
    op.create_table(
        "fire_perimeters",
        id_column(),
        *timestamps(),
        *lineage_columns(),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("incidents.id"), nullable=False),
        spatial_column(),
        sa.Column("original_crs", sa.String(length=64), server_default="EPSG:4326", nullable=False),
        sa.Column("area_hectares", sa.Float(), nullable=True),
        sa.Column("perimeter_kind", sa.String(length=80), server_default="reported", nullable=False),
    )
    op.create_table(
        "official_notices",
        id_column(),
        *timestamps(),
        *lineage_columns(),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("incidents.id"), nullable=True),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=80), nullable=True),
    )
    op.create_table(
        "evacuation_zones",
        id_column(),
        *timestamps(),
        *lineage_columns(),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("incidents.id"), nullable=True),
        spatial_column(),
        sa.Column("original_crs", sa.String(length=64), server_default="EPSG:4326", nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("zone_kind", zone_kind, server_default="evacuation", nullable=False),
        sa.Column("instruction", sa.Text(), nullable=True),
    )
    op.create_table(
        "restriction_zones",
        id_column(),
        *timestamps(),
        *lineage_columns(),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("incidents.id"), nullable=True),
        spatial_column(),
        sa.Column("original_crs", sa.String(length=64), server_default="EPSG:4326", nullable=False),
        sa.Column("name", sa.String(length=180), nullable=False),
        sa.Column("zone_kind", zone_kind, server_default="restriction", nullable=False),
        sa.Column("restriction_type", sa.String(length=120), nullable=False),
    )
    op.create_table(
        "road_segments",
        id_column(),
        *timestamps(),
        *lineage_columns(),
        spatial_column(geometry_type="LINESTRING"),
        sa.Column("original_crs", sa.String(length=64), server_default="EPSG:4326", nullable=False),
        sa.Column("name", sa.String(length=160), nullable=True),
        sa.Column("road_ref", sa.String(length=80), nullable=True),
        sa.Column("road_class", sa.String(length=80), nullable=True),
        sa.Column("surface", sa.String(length=80), nullable=True),
        sa.Column("width_meters", sa.Float(), nullable=True),
        sa.Column("access", sa.String(length=80), nullable=True),
        sa.Column("max_weight_tons", sa.Float(), nullable=True),
        sa.Column("incline", sa.String(length=80), nullable=True),
    )
    op.create_table(
        "road_incidents",
        id_column(),
        *timestamps(),
        *lineage_columns(),
        sa.Column("road_segment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("road_segments.id"), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("incidents.id"), nullable=True),
        sa.Column("kind", road_incident_kind, nullable=False),
        sa.Column("explanation", sa.Text(), nullable=True),
    )
    op.create_table(
        "weather_observations",
        id_column(),
        *timestamps(),
        *lineage_columns(),
        spatial_column(geometry_type="POINT"),
        sa.Column("original_crs", sa.String(length=64), server_default="EPSG:4326", nullable=False),
        sa.Column("station_id", sa.String(length=120), nullable=True),
        sa.Column("wind_speed_kph", sa.Float(), nullable=True),
        sa.Column("wind_direction_degrees", sa.Float(), nullable=True),
        sa.Column("wind_gust_kph", sa.Float(), nullable=True),
        sa.Column("temperature_celsius", sa.Float(), nullable=True),
        sa.Column("humidity_percent", sa.Float(), nullable=True),
        sa.Column("precipitation_mm", sa.Float(), nullable=True),
    )
    op.create_table(
        "weather_forecasts",
        id_column(),
        *timestamps(),
        *lineage_columns(),
        spatial_column(geometry_type="POINT"),
        sa.Column("original_crs", sa.String(length=64), server_default="EPSG:4326", nullable=False),
        sa.Column("forecast_for", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_hours", sa.Integer(), nullable=False),
        sa.Column("resolution", sa.String(length=80), nullable=True),
        sa.Column("wind_speed_kph", sa.Float(), nullable=True),
        sa.Column("wind_direction_degrees", sa.Float(), nullable=True),
        sa.Column("wind_gust_kph", sa.Float(), nullable=True),
        sa.Column("temperature_celsius", sa.Float(), nullable=True),
        sa.Column("humidity_percent", sa.Float(), nullable=True),
        sa.Column("precipitation_mm", sa.Float(), nullable=True),
    )
    op.create_table(
        "smoke_forecasts",
        id_column(),
        *timestamps(),
        *lineage_columns(),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("incidents.id"), nullable=True),
        sa.Column("model_execution_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("model_executions.id"), nullable=False),
        spatial_column(),
        sa.Column("original_crs", sa.String(length=64), server_default="EPSG:4326", nullable=False),
        sa.Column("horizon_hours", sa.Integer(), nullable=False),
        sa.Column("intensity", sa.Float(), nullable=True),
        sa.Column("uncertainty", sa.Float(), nullable=True),
        sa.Column("visibility_impact", sa.String(length=120), nullable=True),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.CheckConstraint("provenance <> 'official'", name="ck_smoke_forecasts_not_official"),
    )
    op.create_table(
        "risk_forecasts",
        id_column(),
        *timestamps(),
        *lineage_columns(),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("incidents.id"), nullable=True),
        sa.Column("model_execution_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("model_executions.id"), nullable=False),
        spatial_column(),
        sa.Column("original_crs", sa.String(length=64), server_default="EPSG:4326", nullable=False),
        sa.Column("risk_type", sa.String(length=120), nullable=False),
        sa.Column("risk_score", sa.Float(), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("factors", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.CheckConstraint("provenance <> 'official'", name="ck_risk_forecasts_not_official"),
        sa.CheckConstraint("risk_score >= 0 AND risk_score <= 1", name="ck_risk_forecasts_score"),
    )
    op.create_table(
        "audit_events",
        id_column(),
        *timestamps(),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("action", sa.String(length=160), nullable=False),
        sa.Column("resource_type", sa.String(length=120), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(length=80), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )

    for table, _geometry_type in table_specs:
        op.create_index(f"ix_{table}_geometry", table, ["geometry"], postgresql_using="gist")
        create_lineage_indexes(table)
    create_lineage_indexes("official_notices")
    op.create_index("ix_incident_versions_incident_version", "incident_versions", ["incident_id", "version"])
    op.create_index("ix_audit_events_user_time", "audit_events", ["user_id", "occurred_at"])
    op.create_index("ix_audit_events_resource", "audit_events", ["resource_type", "resource_id"])


def downgrade() -> None:
    for table in (
        "audit_events",
        "risk_forecasts",
        "smoke_forecasts",
        "weather_forecasts",
        "weather_observations",
        "road_incidents",
        "road_segments",
        "restriction_zones",
        "evacuation_zones",
        "official_notices",
        "fire_perimeters",
        "fire_detections",
        "model_executions",
        "incident_versions",
        "incidents",
        "data_ingestion_runs",
        "users",
        "roles",
        "data_sources",
    ):
        op.drop_table(table)

    for enum in (
        user_role,
        road_incident_kind,
        zone_kind,
        ingestion_run_status,
        incident_status,
        verification_status,
        data_source_type,
        provenance_type,
    ):
        enum.drop(op.get_bind(), checkfirst=True)
