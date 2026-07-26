from datetime import UTC, datetime
from uuid import uuid4

from app.domain.enums import IncidentStatus, ProvenanceType, VerificationStatus
from app.domain.models import DataSource, Incident, ModelExecution, SmokeForecast


def make_data_source(name: str = "NASA FIRMS") -> DataSource:
    return DataSource(
        id=uuid4(),
        name=name,
        source_type=ProvenanceType.OBSERVED,
        authority="NASA",
        reliability_score=0.8,
    )


def make_incident(source: DataSource | None = None) -> Incident:
    return Incident(
        id=uuid4(),
        title="Test wildfire",
        status=IncidentStatus.ACTIVE,
        summary="Fixture incident",
        geometry="POINT(-3.7 40.4)",
        source_id=source.id if source else None,
        provenance=ProvenanceType.OBSERVED,
        verification_status=VerificationStatus.PENDING,
        confidence=0.7,
        observed_at=datetime.now(UTC),
        original_metadata={"fixture": True},
    )


def make_model_execution() -> ModelExecution:
    now = datetime.now(UTC)
    return ModelExecution(
        id=uuid4(),
        model_name="test-smoke",
        model_version="0.1.0",
        started_at=now,
        finished_at=now,
        input_refs={"incident_id": "fixture"},
        input_hash="fixture-input-hash",
        status="completed",
    )


def make_smoke_forecast(execution: ModelExecution) -> SmokeForecast:
    return SmokeForecast(
        id=uuid4(),
        model_execution_id=execution.id,
        horizon_hours=3,
        geometry="POLYGON((-3.8 40.3,-3.6 40.3,-3.6 40.5,-3.8 40.5,-3.8 40.3))",
        provenance=ProvenanceType.ESTIMATED,
        verification_status=VerificationStatus.PENDING,
        confidence=0.55,
        original_metadata={"fixture": True},
    )
