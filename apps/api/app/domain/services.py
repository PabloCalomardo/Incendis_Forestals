from datetime import UTC, datetime

from app.domain.enums import ProvenanceType
from app.domain.models import Incident, IncidentVersion, RiskForecast, SmokeForecast


class LineagePolicyError(ValueError):
    pass


def ensure_prediction_is_not_official(provenance: ProvenanceType) -> None:
    if provenance == ProvenanceType.OFFICIAL:
        raise LineagePolicyError("Prediction records cannot be marked as official data")


def snapshot_incident(incident: Incident, reason: str | None = None) -> IncidentVersion:
    return IncidentVersion(
        incident_id=incident.id,
        version=incident.version,
        status=incident.status,
        title=incident.title,
        snapshot={
            "title": incident.title,
            "status": incident.status.value,
            "summary": incident.summary,
            "provenance": incident.provenance.value,
            "source_id": str(incident.source_id) if incident.source_id else None,
            "external_id": incident.external_id,
            "observed_at": incident.observed_at.isoformat() if incident.observed_at else None,
            "published_at": incident.published_at.isoformat() if incident.published_at else None,
            "received_at": incident.received_at.isoformat() if incident.received_at else None,
            "version": incident.version,
        },
        change_reason=reason,
    )


def bump_incident_version(incident: Incident, reason: str | None = None) -> IncidentVersion:
    version = snapshot_incident(incident, reason)
    incident.version += 1
    incident.updated_at = datetime.now(UTC)
    return version


def validate_forecast_lineage(forecast: SmokeForecast | RiskForecast) -> None:
    ensure_prediction_is_not_official(forecast.provenance)
    if forecast.model_execution_id is None:
        raise LineagePolicyError("Forecast records require a model execution")
