from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.api.routes.civil import CivilQuery, _detection_properties, _lineage, apply_spatial_filters
from app.domain.enums import ProvenanceType
from app.domain.factories import make_data_source, make_incident
from app.domain.models import FireDetection
from app.main import create_app


def test_civil_openapi_exposes_public_contract() -> None:
    client = TestClient(create_app())

    schema = client.get("/openapi.json").json()

    assert "/civil/incidents" in schema["paths"]
    assert "/civil/incidents/{incident_id}/timeline" in schema["paths"]
    assert "/civil/detections" in schema["paths"]
    assert "/civil/perimeters" in schema["paths"]
    assert "/civil/evacuations" in schema["paths"]
    assert "/civil/restrictions" in schema["paths"]
    assert "/civil/roads" in schema["paths"]
    assert "/civil/notices" in schema["paths"]
    assert "/civil/risk" in schema["paths"]
    assert "/civil/smoke" in schema["paths"]
    assert "/civil/search/geographic" in schema["paths"]
    assert "/civil/search/municipality" in schema["paths"]
    assert "/civil/municipalities/search" in schema["paths"]


def test_public_lineage_does_not_expose_internal_fields() -> None:
    source = make_data_source()
    source.base_url = "https://example.test/public"
    incident = make_incident(source)
    incident.original_metadata = {"raw": "secret-ish"}
    incident.deduplication_hash = "internal-hash"

    payload = _lineage(incident, "incident", source, None)

    assert payload["data_type"] == "incident"
    assert payload["source"]["name"] == source.name
    assert payload["source"]["url"] == source.base_url
    assert "original_metadata" not in payload
    assert "deduplication_hash" not in payload
    assert "source_metadata" not in payload


def test_old_estimates_are_not_marked_current() -> None:
    source = make_data_source("Model")
    incident = make_incident(source)
    incident.provenance = ProvenanceType.ESTIMATED
    incident.observed_at = datetime.now(UTC) - timedelta(days=2)

    payload = _lineage(incident, "incident", source, None)

    assert payload["is_current"] is False
    assert "old_estimate_not_current" in payload["warnings"]


def test_spatial_filters_compile_to_postgis_indexable_functions() -> None:
    query = CivilQuery(
        bbox="-10,35,5,44",
        latitude=40.4,
        longitude=-3.7,
        radius_meters=10_000,
    )

    statement = apply_spatial_filters(select(FireDetection), FireDetection, query)
    compiled = str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]

    assert "ST_Intersects" in compiled
    assert "ST_DWithin" in compiled


def test_detection_properties_expose_firms_pixel_dimensions() -> None:
    detection = FireDetection(
        source_id=make_data_source().id,
        external_id="firms-pixel",
        observed_at=datetime.now(UTC),
        received_at=datetime.now(UTC),
        geometry="POINT(-3.7 40.4)",
        latitude=40.4,
        longitude=-3.7,
        sensor="VIIRS",
        satellite="NOAA-20",
        original_metadata={"scan": "0.40", "track": "0.37"},
        deduplication_hash="firms-pixel",
    )

    properties = _detection_properties(detection)

    assert properties["scan_km"] == 0.4
    assert properties["track_km"] == 0.37
