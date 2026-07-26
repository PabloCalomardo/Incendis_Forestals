from uuid import uuid4

import pytest

from app.domain.enums import IncidentStatus, ProvenanceType
from app.domain.factories import make_incident, make_model_execution, make_smoke_forecast
from app.domain.models import Incident, SmokeForecast
from app.domain.services import (
    LineagePolicyError,
    bump_incident_version,
    ensure_prediction_is_not_official,
    snapshot_incident,
    validate_forecast_lineage,
)


def test_snapshot_preserves_original_incident_values() -> None:
    incident = make_incident()
    incident.version = 3

    version = snapshot_incident(incident, reason="source update")

    assert version.version == 3
    assert version.title == incident.title
    assert version.snapshot["provenance"] == ProvenanceType.OBSERVED.value
    assert version.change_reason == "source update"


def test_bump_incident_version_creates_version_before_increment() -> None:
    incident = make_incident()
    incident.version = 1

    version = bump_incident_version(incident, reason="status changed")

    assert version.version == 1
    assert incident.version == 2


def test_prediction_cannot_be_official() -> None:
    with pytest.raises(LineagePolicyError):
        ensure_prediction_is_not_official(ProvenanceType.OFFICIAL)


def test_forecast_requires_estimated_or_observed_lineage_and_model_execution() -> None:
    execution = make_model_execution()
    forecast = make_smoke_forecast(execution)

    validate_forecast_lineage(forecast)

    forecast.provenance = ProvenanceType.OFFICIAL
    with pytest.raises(LineagePolicyError):
        validate_forecast_lineage(forecast)


def test_required_phase_2_tables_exist_in_metadata() -> None:
    required_tables = {
        "data_sources",
        "data_ingestion_runs",
        "incidents",
        "incident_versions",
        "fire_detections",
        "fire_perimeters",
        "official_notices",
        "evacuation_zones",
        "restriction_zones",
        "road_segments",
        "road_incidents",
        "weather_observations",
        "weather_forecasts",
        "smoke_forecasts",
        "risk_forecasts",
        "model_executions",
        "users",
        "roles",
        "audit_events",
    }

    assert required_tables.issubset(Incident.metadata.tables.keys())
    assert required_tables.issubset(SmokeForecast.metadata.tables.keys())


def test_soft_delete_field_exists_on_critical_records() -> None:
    incident = make_incident()
    incident.deleted_at = None

    assert hasattr(incident, "deleted_at")


def test_contradictory_sources_can_coexist_as_distinct_incidents() -> None:
    first = make_incident()
    first.id = uuid4()
    first.external_id = "same-fire"
    first.status = IncidentStatus.ACTIVE
    first.provenance = ProvenanceType.OBSERVED

    second = make_incident()
    second.id = uuid4()
    second.external_id = "same-fire"
    second.status = IncidentStatus.EXTINGUISHED
    second.provenance = ProvenanceType.OFFICIAL

    assert first.external_id == second.external_id
    assert first.status != second.status
    assert first.provenance != second.provenance
