from datetime import datetime
from enum import Enum as PythonEnum
from uuid import UUID

from geoalchemy2 import Geometry
from sqlalchemy import CheckConstraint, DateTime, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.domain.base import Base, IdMixin, TimestampMixin
from app.domain.enums import (
    IncidentStatus,
    IngestionRunStatus,
    ProvenanceType,
    RoadIncidentKind,
    UserRole,
    VerificationStatus,
    ZoneKind,
)

JSONDict = dict[str, object]


def enum_values(enum_class: type[PythonEnum]) -> list[str]:
    return [str(member.value) for member in enum_class]


class LineageMixin:
    source_id: Mapped[UUID | None] = mapped_column(ForeignKey("data_sources.id"), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provenance: Mapped[ProvenanceType] = mapped_column(
        Enum(ProvenanceType, name="provenance_type", values_callable=enum_values), nullable=False
    )
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status", values_callable=enum_values),
        default=VerificationStatus.PENDING,
        nullable=False,
    )
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    original_metadata: Mapped[JSONDict] = mapped_column(JSONB, default=dict, nullable=False)
    deduplication_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)


class SpatialMixin:
    geometry: Mapped[str] = mapped_column(Geometry(geometry_type="GEOMETRY", srid=4326), nullable=False)
    original_crs: Mapped[str] = mapped_column(String(64), default="EPSG:4326", nullable=False)


class DataSource(Base, IdMixin, TimestampMixin):
    __tablename__ = "data_sources"

    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    source_type: Mapped[ProvenanceType] = mapped_column(
        Enum(ProvenanceType, name="data_source_type", values_callable=enum_values), nullable=False
    )
    authority: Mapped[str | None] = mapped_column(String(160), nullable=True)
    base_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    attribution: Mapped[str | None] = mapped_column(Text, nullable=True)
    update_frequency: Mapped[str | None] = mapped_column(String(120), nullable=True)
    expected_delay_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reliability_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_metadata: Mapped[JSONDict] = mapped_column(JSONB, default=dict, nullable=False)


class DataIngestionRun(Base, IdMixin, TimestampMixin):
    __tablename__ = "data_ingestion_runs"

    source_id: Mapped[UUID] = mapped_column(ForeignKey("data_sources.id"), nullable=False)
    connector_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[IngestionRunStatus] = mapped_column(
        Enum(IngestionRunStatus, name="ingestion_run_status", values_callable=enum_values), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    discarded_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    persisted_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    raw_object_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_summary: Mapped[JSONDict] = mapped_column(JSONB, default=dict, nullable=False)
    metrics: Mapped[JSONDict] = mapped_column(JSONB, default=dict, nullable=False)


class Incident(Base, IdMixin, TimestampMixin, LineageMixin, SpatialMixin):
    __tablename__ = "incidents"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_incidents_confidence",
        ),
    )

    title: Mapped[str] = mapped_column(String(240), nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status", values_callable=enum_values), nullable=False
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)


class IncidentVersion(Base, IdMixin, TimestampMixin):
    __tablename__ = "incident_versions"

    incident_id: Mapped[UUID] = mapped_column(ForeignKey("incidents.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(
        Enum(IncidentStatus, name="incident_status", values_callable=enum_values), nullable=False
    )
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    snapshot: Mapped[JSONDict] = mapped_column(JSONB, nullable=False)
    changed_by_user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)


class FireDetection(Base, IdMixin, TimestampMixin, LineageMixin):
    __tablename__ = "fire_detections"
    __table_args__ = (
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_fire_detections_confidence",
        ),
    )

    incident_id: Mapped[UUID | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    geometry: Mapped[str] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    original_crs: Mapped[str] = mapped_column(String(64), default="EPSG:4326", nullable=False)
    sensor: Mapped[str | None] = mapped_column(String(80), nullable=True)
    satellite: Mapped[str | None] = mapped_column(String(80), nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    frp_mw: Mapped[float | None] = mapped_column(Float, nullable=True)


class FirePerimeter(Base, IdMixin, TimestampMixin, LineageMixin, SpatialMixin):
    __tablename__ = "fire_perimeters"

    incident_id: Mapped[UUID] = mapped_column(ForeignKey("incidents.id"), nullable=False)
    area_hectares: Mapped[float | None] = mapped_column(Float, nullable=True)
    perimeter_kind: Mapped[str] = mapped_column(String(80), default="reported", nullable=False)


class OfficialNotice(Base, IdMixin, TimestampMixin, LineageMixin):
    __tablename__ = "official_notices"

    incident_id: Mapped[UUID | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str | None] = mapped_column(String(80), nullable=True)


class EvacuationZone(Base, IdMixin, TimestampMixin, LineageMixin, SpatialMixin):
    __tablename__ = "evacuation_zones"

    incident_id: Mapped[UUID | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    zone_kind: Mapped[ZoneKind] = mapped_column(
        Enum(ZoneKind, name="zone_kind", values_callable=enum_values), default=ZoneKind.EVACUATION, nullable=False
    )
    instruction: Mapped[str | None] = mapped_column(Text, nullable=True)


class RestrictionZone(Base, IdMixin, TimestampMixin, LineageMixin, SpatialMixin):
    __tablename__ = "restriction_zones"

    incident_id: Mapped[UUID | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    zone_kind: Mapped[ZoneKind] = mapped_column(
        Enum(ZoneKind, name="zone_kind", values_callable=enum_values), default=ZoneKind.RESTRICTION, nullable=False
    )
    restriction_type: Mapped[str] = mapped_column(String(120), nullable=False)


class RoadSegment(Base, IdMixin, TimestampMixin, LineageMixin):
    __tablename__ = "road_segments"

    geometry: Mapped[str] = mapped_column(
        Geometry(geometry_type="LINESTRING", srid=4326), nullable=False
    )
    original_crs: Mapped[str] = mapped_column(String(64), default="EPSG:4326", nullable=False)
    name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    road_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    road_class: Mapped[str | None] = mapped_column(String(80), nullable=True)
    surface: Mapped[str | None] = mapped_column(String(80), nullable=True)
    width_meters: Mapped[float | None] = mapped_column(Float, nullable=True)
    access: Mapped[str | None] = mapped_column(String(80), nullable=True)
    max_weight_tons: Mapped[float | None] = mapped_column(Float, nullable=True)
    incline: Mapped[str | None] = mapped_column(String(80), nullable=True)


class RoadIncident(Base, IdMixin, TimestampMixin, LineageMixin):
    __tablename__ = "road_incidents"

    road_segment_id: Mapped[UUID] = mapped_column(ForeignKey("road_segments.id"), nullable=False)
    incident_id: Mapped[UUID | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    kind: Mapped[RoadIncidentKind] = mapped_column(
        Enum(RoadIncidentKind, name="road_incident_kind", values_callable=enum_values), nullable=False
    )
    explanation: Mapped[str | None] = mapped_column(Text, nullable=True)


class WeatherObservation(Base, IdMixin, TimestampMixin, LineageMixin):
    __tablename__ = "weather_observations"

    geometry: Mapped[str] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    original_crs: Mapped[str] = mapped_column(String(64), default="EPSG:4326", nullable=False)
    station_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    wind_speed_kph: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction_degrees: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_gust_kph: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_celsius: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_mm: Mapped[float | None] = mapped_column(Float, nullable=True)


class WeatherForecast(Base, IdMixin, TimestampMixin, LineageMixin):
    __tablename__ = "weather_forecasts"

    geometry: Mapped[str] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)
    original_crs: Mapped[str] = mapped_column(String(64), default="EPSG:4326", nullable=False)
    forecast_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution: Mapped[str | None] = mapped_column(String(80), nullable=True)
    wind_speed_kph: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_direction_degrees: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_gust_kph: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_celsius: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    precipitation_mm: Mapped[float | None] = mapped_column(Float, nullable=True)


class ModelExecution(Base, IdMixin, TimestampMixin):
    __tablename__ = "model_executions"

    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str] = mapped_column(String(80), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    input_refs: Mapped[JSONDict] = mapped_column(JSONB, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    parameters: Mapped[JSONDict] = mapped_column(JSONB, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(60), nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)


class SmokeForecast(Base, IdMixin, TimestampMixin, LineageMixin, SpatialMixin):
    __tablename__ = "smoke_forecasts"

    incident_id: Mapped[UUID | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    model_execution_id: Mapped[UUID] = mapped_column(ForeignKey("model_executions.id"), nullable=False)
    horizon_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    intensity: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertainty: Mapped[float | None] = mapped_column(Float, nullable=True)
    visibility_impact: Mapped[str | None] = mapped_column(String(120), nullable=True)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)


class RiskForecast(Base, IdMixin, TimestampMixin, LineageMixin, SpatialMixin):
    __tablename__ = "risk_forecasts"

    incident_id: Mapped[UUID | None] = mapped_column(ForeignKey("incidents.id"), nullable=True)
    model_execution_id: Mapped[UUID] = mapped_column(ForeignKey("model_executions.id"), nullable=False)
    risk_type: Mapped[str] = mapped_column(String(120), nullable=False)
    risk_score: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False)
    factors: Mapped[JSONDict] = mapped_column(JSONB, default=dict, nullable=False)


class Role(Base, IdMixin, TimestampMixin):
    __tablename__ = "roles"

    name: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=enum_values), nullable=False, unique=True
    )
    permissions: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)


class User(Base, IdMixin, TimestampMixin):
    __tablename__ = "users"

    external_subject: Mapped[str] = mapped_column(String(240), nullable=False, unique=True)
    email: Mapped[str | None] = mapped_column(String(240), nullable=True)
    display_name: Mapped[str | None] = mapped_column(String(240), nullable=True)
    role_id: Mapped[UUID] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    role: Mapped[Role] = relationship()


class AuditEvent(Base, IdMixin, TimestampMixin):
    __tablename__ = "audit_events"

    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_id: Mapped[UUID | None] = mapped_column(PgUUID(as_uuid=True), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[JSONDict] = mapped_column(JSONB, default=dict, nullable=False)


class ConfidenceAssessment(Base, IdMixin, TimestampMixin):
    __tablename__ = "confidence_assessments"

    resource_type: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(80), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    factors: Mapped[JSONDict] = mapped_column(JSONB, default=dict, nullable=False)
    penalties: Mapped[JSONDict] = mapped_column(JSONB, default=dict, nullable=False)
    warnings: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)


class DataConflict(Base, IdMixin, TimestampMixin):
    __tablename__ = "data_conflicts"

    conflict_type: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    conflicting_resource_type: Mapped[str] = mapped_column(String(120), nullable=False)
    conflicting_resource_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    severity: Mapped[str] = mapped_column(String(40), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[JSONDict] = mapped_column(JSONB, default=dict, nullable=False)


class ObservationLink(Base, IdMixin, TimestampMixin):
    __tablename__ = "observation_links"

    resource_type: Mapped[str] = mapped_column(String(120), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    related_resource_type: Mapped[str] = mapped_column(String(120), nullable=False)
    related_resource_id: Mapped[UUID] = mapped_column(PgUUID(as_uuid=True), nullable=False)
    relation_kind: Mapped[str] = mapped_column(String(120), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[JSONDict] = mapped_column(JSONB, default=dict, nullable=False)
