from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.domain.enums import IncidentStatus, ProvenanceType
from app.schemas.domain import IncidentCreate, RiskForecastCreate


def test_incident_create_requires_provenance() -> None:
    incident = IncidentCreate(
        title="Observed fire",
        status=IncidentStatus.ACTIVE,
        geometry="POINT(-3.7 40.4)",
        provenance=ProvenanceType.OBSERVED,
        observed_at=datetime.now(UTC),
    )

    assert incident.provenance == ProvenanceType.OBSERVED
    assert incident.original_metadata == {}


def test_confidence_is_bounded() -> None:
    with pytest.raises(ValidationError):
        IncidentCreate(
            title="Bad confidence",
            status=IncidentStatus.ACTIVE,
            geometry="POINT(-3.7 40.4)",
            provenance=ProvenanceType.UNVERIFIED,
            confidence=1.5,
        )


def test_risk_forecast_requires_model_execution_trace() -> None:
    model_execution_id = uuid4()
    forecast = RiskForecastCreate(
        model_execution_id=model_execution_id,
        geometry="POLYGON((-3.8 40.3,-3.6 40.3,-3.6 40.5,-3.8 40.5,-3.8 40.3))",
        provenance=ProvenanceType.ESTIMATED,
        risk_type="fire_spread",
        risk_score=0.42,
        category="medium",
    )

    assert forecast.model_execution_id == model_execution_id
    assert forecast.provenance == ProvenanceType.ESTIMATED
