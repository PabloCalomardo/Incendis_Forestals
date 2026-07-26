from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    IngestionRunStatus,
    IncidentStatus,
    ProvenanceType,
    RoadIncidentKind,
    UserRole,
    VerificationStatus,
    ZoneKind,
)


class LineageCreate(BaseModel):
    source_id: UUID | None = None
    external_id: str | None = None
    provenance: ProvenanceType
    observed_at: datetime | None = None
    published_at: datetime | None = None
    received_at: datetime | None = None
    expires_at: datetime | None = None
    verification_status: VerificationStatus = VerificationStatus.PENDING
    confidence: float | None = Field(default=None, ge=0, le=1)
    original_metadata: dict[str, object] = Field(default_factory=dict)
    deduplication_hash: str | None = None


class SpatialCreate(BaseModel):
    geometry: str
    original_crs: str = "EPSG:4326"


class DomainRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None


class LineageRead(DomainRead):
    source_id: UUID | None
    external_id: str | None
    provenance: ProvenanceType
    observed_at: datetime | None
    published_at: datetime | None
    received_at: datetime | None
    expires_at: datetime | None
    verification_status: VerificationStatus
    confidence: float | None
    version: int
    original_metadata: dict[str, object]
    deduplication_hash: str | None


class DataSourceCreate(BaseModel):
    name: str
    source_type: ProvenanceType
    authority: str | None = None
    base_url: str | None = None
    license_name: str | None = None
    attribution: str | None = None
    update_frequency: str | None = None
    expected_delay_seconds: int | None = None
    reliability_score: float | None = Field(default=None, ge=0, le=1)
    source_metadata: dict[str, object] = Field(default_factory=dict)


class DataSourceRead(DomainRead, DataSourceCreate):
    pass


class DataIngestionRunCreate(BaseModel):
    source_id: UUID
    connector_name: str
    status: IngestionRunStatus
    started_at: datetime
    finished_at: datetime | None = None
    received_count: int = 0
    discarded_count: int = 0
    duplicate_count: int = 0
    persisted_count: int = 0
    raw_object_uri: str | None = None
    error_summary: dict[str, object] = Field(default_factory=dict)
    metrics: dict[str, object] = Field(default_factory=dict)


class DataIngestionRunRead(DomainRead, DataIngestionRunCreate):
    pass


class IncidentCreate(LineageCreate, SpatialCreate):
    title: str
    status: IncidentStatus
    summary: str | None = None


class IncidentRead(LineageRead):
    geometry: str
    original_crs: str
    title: str
    status: IncidentStatus
    summary: str | None


class IncidentVersionCreate(BaseModel):
    incident_id: UUID
    version: int
    status: IncidentStatus
    title: str
    snapshot: dict[str, object]
    changed_by_user_id: UUID | None = None
    change_reason: str | None = None


class IncidentVersionRead(DomainRead, IncidentVersionCreate):
    pass


class FireDetectionCreate(LineageCreate):
    incident_id: UUID | None = None
    geometry: str
    original_crs: str = "EPSG:4326"
    sensor: str | None = None
    satellite: str | None = None
    latitude: float
    longitude: float
    frp_mw: float | None = None


class FireDetectionRead(LineageRead, FireDetectionCreate):
    pass


class FirePerimeterCreate(LineageCreate, SpatialCreate):
    incident_id: UUID
    area_hectares: float | None = None
    perimeter_kind: str = "reported"


class FirePerimeterRead(LineageRead, FirePerimeterCreate):
    pass


class OfficialNoticeCreate(LineageCreate):
    incident_id: UUID | None = None
    title: str
    body: str
    url: str | None = None
    severity: str | None = None


class OfficialNoticeRead(LineageRead, OfficialNoticeCreate):
    pass


class ZoneCreate(LineageCreate, SpatialCreate):
    incident_id: UUID | None = None
    name: str
    zone_kind: ZoneKind
    instruction: str | None = None
    restriction_type: str | None = None


class ZoneRead(LineageRead, ZoneCreate):
    pass


class RoadSegmentCreate(LineageCreate):
    geometry: str
    original_crs: str = "EPSG:4326"
    name: str | None = None
    road_ref: str | None = None
    road_class: str | None = None
    surface: str | None = None
    width_meters: float | None = None
    access: str | None = None
    max_weight_tons: float | None = None
    incline: str | None = None


class RoadSegmentRead(LineageRead, RoadSegmentCreate):
    pass


class RoadIncidentCreate(LineageCreate):
    road_segment_id: UUID
    incident_id: UUID | None = None
    kind: RoadIncidentKind
    explanation: str | None = None


class RoadIncidentRead(LineageRead, RoadIncidentCreate):
    pass


class WeatherObservationCreate(LineageCreate):
    geometry: str
    original_crs: str = "EPSG:4326"
    station_id: str | None = None
    wind_speed_kph: float | None = None
    wind_direction_degrees: float | None = None
    wind_gust_kph: float | None = None
    temperature_celsius: float | None = None
    humidity_percent: float | None = None
    precipitation_mm: float | None = None


class WeatherObservationRead(LineageRead, WeatherObservationCreate):
    pass


class WeatherForecastCreate(WeatherObservationCreate):
    forecast_for: datetime
    horizon_hours: int
    resolution: str | None = None


class WeatherForecastRead(LineageRead, WeatherForecastCreate):
    pass


class ModelExecutionCreate(BaseModel):
    model_name: str
    model_version: str
    started_at: datetime
    finished_at: datetime | None = None
    input_refs: dict[str, object]
    input_hash: str
    parameters: dict[str, object] = Field(default_factory=dict)
    status: str
    warnings: list[str] = Field(default_factory=list)


class ModelExecutionRead(DomainRead, ModelExecutionCreate):
    pass


class SmokeForecastCreate(LineageCreate, SpatialCreate):
    incident_id: UUID | None = None
    model_execution_id: UUID
    horizon_hours: int
    intensity: float | None = None
    uncertainty: float | None = None
    visibility_impact: str | None = None
    warnings: list[str] = Field(default_factory=list)


class SmokeForecastRead(LineageRead, SmokeForecastCreate):
    pass


class RiskForecastCreate(LineageCreate, SpatialCreate):
    incident_id: UUID | None = None
    model_execution_id: UUID
    risk_type: str
    risk_score: float = Field(ge=0, le=1)
    category: str
    factors: dict[str, object] = Field(default_factory=dict)


class RiskForecastRead(LineageRead, RiskForecastCreate):
    pass


class RoleCreate(BaseModel):
    name: UserRole
    permissions: list[str] = Field(default_factory=list)


class RoleRead(DomainRead, RoleCreate):
    pass


class UserCreate(BaseModel):
    external_subject: str
    email: str | None = None
    display_name: str | None = None
    role_id: UUID
    is_active: bool = True


class UserRead(DomainRead, UserCreate):
    pass


class AuditEventCreate(BaseModel):
    user_id: UUID | None = None
    action: str
    resource_type: str
    resource_id: UUID | None = None
    occurred_at: datetime
    ip_address: str | None = None
    user_agent: str | None = None
    details: dict[str, object] = Field(default_factory=dict)


class AuditEventRead(DomainRead, AuditEventCreate):
    pass
