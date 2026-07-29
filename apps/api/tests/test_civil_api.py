from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.api.routes.civil import (
    CivilQuery,
    _apply_common_filters,
    _confirmed_extinction_date,
    _detection_properties,
    _incident_properties,
    _lineage,
    _perimeter_properties,
    apply_spatial_filters,
)
from app.domain.enums import ProvenanceType
from app.domain.factories import make_data_source, make_incident
from app.domain.models import FireDetection, FirePerimeter
from app.main import create_app


def test_civil_openapi_exposes_public_contract() -> None:
    client = TestClient(create_app())

    schema = client.get("/openapi.json").json()

    assert "/civil/incidents" in schema["paths"]
    assert "/civil/incidents/{incident_id}/timeline" in schema["paths"]
    assert "/civil/detections" in schema["paths"]
    assert "/civil/detections/timeline" in schema["paths"]
    assert "/civil/perimeters" in schema["paths"]
    assert "/civil/evacuations" in schema["paths"]
    assert "/civil/es-alerts" in schema["paths"]
    assert "/civil/restrictions" in schema["paths"]
    assert "/civil/roads" in schema["paths"]
    assert "/civil/notices" in schema["paths"]
    assert "/civil/risk" in schema["paths"]
    assert "/civil/smoke" in schema["paths"]
    assert "/civil/search/geographic" in schema["paths"]
    assert "/civil/search/municipality" in schema["paths"]
    assert "/civil/municipalities/search" in schema["paths"]
    assert "/internal/ingestion/es-alert/sync" in schema["paths"]
    assert "/civil/osint/incidents" in schema["paths"]
    assert "/civil/osint/incidents/{incident_id}" in schema["paths"]
    assert "/civil/osint/x-accounts" in schema["paths"]
    assert "/internal/ingestion/osint/run" in schema["paths"]
    assert "/internal/ingestion/osint/review/{publication_id}" in schema["paths"]


def test_institutional_x_accounts_are_human_review_only() -> None:
    client = TestClient(create_app())

    response = client.get("/civil/osint/x-accounts")
    payload = response.json()

    assert response.status_code == 200
    assert payload["automated_collection"] is False
    assert payload["collection_mode"] == "human_review"
    assert payload["primary_gateway"] == "nitter"
    handles = {item["handle"] for item in payload["items"]}
    assert {"bomberscat", "emergenciescat", "proteccioncivil"} <= handles


def test_es_alert_empty_snapshot_requires_explicit_confirmation() -> None:
    client = TestClient(create_app())

    response = client.post(
        "/internal/ingestion/es-alert/sync",
        headers={"x-internal-token": "change-me-local-internal-token"},
        json={
            "source_generated_at": "2026-07-28T12:00:00Z",
            "complete_snapshot": True,
            "alerts": [],
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "Empty ES-Alert snapshot requires allow_empty_snapshot=true"


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


def test_linked_firms_detections_remain_visible_in_public_queries() -> None:
    statement = _apply_common_filters(select(FireDetection), FireDetection, CivilQuery())
    compiled = str(statement.compile(dialect=postgresql.dialect()))  # type: ignore[no-untyped-call]

    assert "fire_detections.incident_id IS NULL" not in compiled


def test_incident_properties_expose_effis_dates_and_shapefile_attributes() -> None:
    incident = make_incident(make_data_source())
    incident.original_metadata = {
        "canonical_fire": True,
        "firedate": "2026-07-27",
        "finaldate": "2026-07-28",
        "area_ha": 128.4,
        "commune": "Municipi prova",
        "shapefile_attributes": {"AREA_HA": 128.4, "CLASS": "Forest"},
    }

    properties = _incident_properties(incident)

    assert properties["fire_date"] == "2026-07-27"
    assert properties["final_date"] is None
    assert properties["area_hectares"] == 128.4
    assert '"CLASS": "Forest"' in properties["effis_attributes_json"]


def test_extinction_date_requires_confirmation_and_a_recent_perimeter_update() -> None:
    now = datetime.now(UTC)
    confirmed = {
        "extinction_confirmed": True,
        "confirmed_extinction_at": now.isoformat(),
        "lastupdate": (now - timedelta(hours=12)).isoformat(),
    }
    stale = {**confirmed, "lastupdate": (now - timedelta(days=4)).isoformat()}
    unconfirmed = {**confirmed, "extinction_confirmed": False}

    assert _confirmed_extinction_date(confirmed) == now.isoformat()
    assert _confirmed_extinction_date(stale) is None
    assert _confirmed_extinction_date(unconfirmed) is None


def test_perimeter_properties_expose_effis_context_and_operational_limit() -> None:
    perimeter = FirePerimeter(
        incident_id=make_incident(make_data_source()).id,
        geometry="POLYGON((-3 40,-2 40,-2 41,-3 40))",
        area_hectares=12.5,
        perimeter_kind="effis_official_burnt_area",
        original_metadata={
            "firedate": "2026-07-20",
            "province": "Madrid",
            "shapefile_attributes": {"ID": "area-1", "CONIFER": 68.0, "CLASS": "Forest"},
            "operational_extinction_status_available": False,
            "operational_extinction_status_note": "EFFIS no publica les tasques operatives d'extincio.",
            "canonical_title": "Incendi #IFSierraOeste - Robledo",
            "canonical_summary": "34 dotacions treballen a la zona.",
            "hashtags": ["#IFSierraOeste"],
            "firms_detection_count": 42,
            "osint_publication_count": 3,
        },
    )

    properties = _perimeter_properties(perimeter)

    assert properties["fire_date"] == "2026-07-20"
    assert properties["province"] == "Madrid"
    assert properties["extinction_operations_available"] is False
    assert properties["canonical_title"] == "Incendi #IFSierraOeste - Robledo"
    assert properties["firms_detection_count"] == 42
    assert properties["osint_publication_count"] == 3
    assert '"CONIFER": 68.0' in properties["effis_attributes_json"]
