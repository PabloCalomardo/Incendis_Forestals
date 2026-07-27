from pathlib import Path

import httpx
import pytest

from app.ingestion.aemet import AemetConnector, AemetRawPayload
from app.ingestion.base import ValidationError
from app.ingestion.config import (
    AemetConnectorConfig,
    DatexConnectorConfig,
    EtrafficConnectorConfig,
    IgnConnectorConfig,
    OsmConnectorConfig,
    ProteccioCivilConnectorConfig,
)
from app.ingestion.datex import DatexRawPayload, DatexTrafficConnector, _dgt_json_payload, _pk_xy_results
from app.ingestion.etraffic import DgtEtrafficConnector
from app.ingestion.ign import IgnTransportConnector
from app.ingestion.osm import OsmRoadConnector
from app.ingestion.proteccio_civil import ProteccioCivilPlansConnector


class DummySession:
    pass


def read_fixture(name: str) -> str:
    return Path(f"apps/api/tests/fixtures/{name}").read_text(encoding="utf-8")


def aemet_config(api_key: str = "test-key") -> AemetConnectorConfig:
    return AemetConnectorConfig(
        api_key=api_key,
        base_url="https://opendata.aemet.es/opendata",
        timeout_seconds=1,
        max_retries=2,
        forecast_municipalities=["28079"],
        forecast_locations={"28079": {"name": "Madrid", "latitude": 40.4168, "longitude": -3.7038}},
    )


def ign_config() -> IgnConnectorConfig:
    return IgnConnectorConfig(
        wfs_base_url="https://api-features.idee.es",
        transport_typename="roadlink",
        area_bbox="-10.0,35.5,4.5,44.5",
        feature_limit=50,
        max_features=2,
        max_pages_per_tile=1,
        tile_size_degrees=20.0,
        target_datex_restrictions=False,
        timeout_seconds=1,
        max_retries=2,
    )


def osm_config() -> OsmConnectorConfig:
    return OsmConnectorConfig(
        overpass_url="https://overpass-api.de/api/interpreter",
        area_bbox="-10.0,35.5,4.5,44.5",
        timeout_seconds=1,
        max_retries=2,
        feature_limit=50,
    )


def datex_config() -> DatexConnectorConfig:
    return DatexConnectorConfig(
        feed_urls=["https://datex.test/content.xml"],
        timeout_seconds=1,
        max_retries=2,
        pk_to_xy_url="https://dgt.test/pkxy",
        pk_to_xy_timeout_seconds=1,
        pk_sample_step_km=1.0,
        pk_sample_budget=10,
        osrm_route_url="https://router.test/route/v1/driving",
        osrm_timeout_seconds=1,
        overpass_url="https://overpass.test/api/interpreter",
        overpass_timeout_seconds=1,
    )


def etraffic_config() -> EtrafficConnectorConfig:
    return EtrafficConnectorConfig(
        base_url="https://etraffic.test/etrafficWEB/api",
        public_url="https://etraffic.test/etrafficWEB/",
        filters_via=["Carreteras cortadas", "Tráfico lento"],
        timeout_seconds=1,
        max_retries=2,
    )


def proteccio_civil_config() -> ProteccioCivilConnectorConfig:
    return ProteccioCivilConnectorConfig(
        plans_url="https://proteccio-civil.test/plans.json",
        timeout_seconds=1,
        max_retries=2,
    )


def test_aemet_normalizes_observations_and_forecasts() -> None:
    connector = AemetConnector(DummySession(), aemet_config())  # type: ignore[arg-type]
    raw = AemetRawPayload(
        observations=read_fixture("aemet_observations.json"),
        forecasts={"28079": read_fixture("aemet_forecast_28079.json")},
    )

    records = connector.normalize(raw)
    unique, duplicates = connector.deduplicate(records)

    assert len(records) == 3
    assert len(unique) == 2
    assert duplicates == 1
    assert any(record.kind == "observation" and record.wind_speed_kph == 18 for record in records)
    assert any(record.kind == "forecast" and record.horizon_hours == 4 for record in records)


@pytest.mark.asyncio
async def test_aemet_fetch_uses_hateoas_datos_urls() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        if "observacion/convencional/todas" in str(request.url):
            return httpx.Response(200, json={"datos": "https://data.aemet.test/observations"})
        if "municipio/horaria/28079" in str(request.url):
            return httpx.Response(200, json={"datos": "https://data.aemet.test/forecast"})
        if str(request.url) == "https://data.aemet.test/observations":
            return httpx.Response(200, text=read_fixture("aemet_observations.json"))
        if str(request.url) == "https://data.aemet.test/forecast":
            return httpx.Response(200, text=read_fixture("aemet_forecast_28079.json"))
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    connector = AemetConnector(DummySession(), aemet_config(), http_client=client)  # type: ignore[arg-type]

    raw = await connector.fetch()

    assert "MADRID, RETIRO" in raw.observations
    assert "api_key=test-key" in requested_urls[0]
    assert "https://data.aemet.test/forecast" in requested_urls
    await client.aclose()


@pytest.mark.asyncio
async def test_aemet_fetch_requires_api_key() -> None:
    connector = AemetConnector(DummySession(), aemet_config(api_key=""))  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="AEMET_API_KEY"):
        await connector.fetch()


def test_ign_normalizes_transport_geojson_and_deduplicates() -> None:
    connector = IgnTransportConnector(DummySession(), ign_config())  # type: ignore[arg-type]
    raw = read_fixture("ign_transport.geojson")

    connector.validate(raw)
    records = connector.normalize(raw)
    unique, duplicates = connector.deduplicate(records)

    assert len(records) == 2
    assert len(unique) == 1
    assert duplicates == 1
    assert records[0].geometry_wkt.startswith("LINESTRING")
    assert records[0].original_metadata["crs"] == "EPSG:4326"


@pytest.mark.asyncio
async def test_ign_fetch_uses_wfs_bbox_and_limit() -> None:
    requested_params: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requested_params
        requested_params = dict(request.url.params)
        return httpx.Response(200, text=read_fixture("ign_transport.geojson"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    connector = IgnTransportConnector(DummySession(), ign_config(), http_client=client)  # type: ignore[arg-type]

    raw = await connector.fetch()

    assert "FeatureCollection" in raw
    assert requested_params["f"] == "json"
    assert requested_params["limit"] == "50"
    assert requested_params["bbox"] == "-10.0,35.5,4.5,44.5"
    await client.aclose()


def test_osm_normalizes_road_tags_and_deduplicates() -> None:
    connector = OsmRoadConnector(DummySession(), osm_config())  # type: ignore[arg-type]
    raw = read_fixture("osm_roads.json")

    connector.validate(raw)
    records = connector.normalize(raw)
    unique, duplicates = connector.deduplicate(records)

    assert len(records) == 2
    assert len(unique) == 1
    assert duplicates == 1
    assert records[0].tags["tracktype"] == "grade2"
    assert records[0].geometry_wkt.startswith("LINESTRING")


def test_osm_query_is_bounded_and_limited() -> None:
    connector = OsmRoadConnector(DummySession(), osm_config())  # type: ignore[arg-type]

    query = connector._query()

    assert 'way["highway"]' in query
    assert "35.5,-10.0,44.5,4.5" in query
    assert "out tags geom 50" in query


def test_datex_normalizes_restrictions_and_deduplicates() -> None:
    connector = DatexTrafficConnector(DummySession(), datex_config())  # type: ignore[arg-type]
    raw = DatexRawPayload(feeds={"https://datex.test/content.xml": read_fixture("datex_sct_sample.xml")})

    connector.validate(raw)
    records = connector.normalize(raw)
    unique, duplicates = connector.deduplicate([*records, *records])

    assert len(records) == 1
    assert len(unique) == 1
    assert duplicates == 1
    assert records[0].road_ref == "N-150"
    assert records[0].geometry_wkt.startswith("LINESTRING")
    assert records[0].kind == "OTRAS AFECCIONES"


def test_datex_parses_nonstandard_dgt_pk_response() -> None:
    raw = "{\"results\":[{\"paramName\":\"localizacion\",\"value\":[[380414.6,4493761.41,'05']]}]}"

    assert _pk_xy_results(_dgt_json_payload(raw)) == [(380414.6, 4493761.41)]


def encode_etraffic(payload: str) -> str:
    import base64

    encoded = bytearray(payload.encode("utf-8"))
    for index, value in enumerate(encoded):
        encoded[index] = value ^ ord("f")
    return base64.b64encode(encoded).decode("ascii")


def test_etraffic_decodes_and_normalizes_detailed_road_geometry() -> None:
    connector = DgtEtrafficConnector(DummySession(), etraffic_config())  # type: ignore[arg-type]
    raw_json = read_fixture("etraffic_filtered_data.json")

    decoded = connector._decode_response(encode_etraffic(raw_json))
    connector.validate(decoded)
    records = connector.normalize(decoded)
    unique, duplicates = connector.deduplicate([*records, *records])

    assert len(records) == 1
    assert len(unique) == 1
    assert duplicates == 1
    assert records[0].road_ref == "A-8005"
    assert records[0].geometry_wkt.startswith("MULTILINESTRING")
    assert len(records[0].segment_wkts) == 2


@pytest.mark.asyncio
async def test_datex_fetch_reads_configured_feeds() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, text=read_fixture("datex_sct_sample.xml"))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    connector = DatexTrafficConnector(DummySession(), datex_config(), http_client=client)  # type: ignore[arg-type]

    raw = await connector.fetch()

    assert requested_urls == ["https://datex.test/content.xml"]
    assert "d2LogicalModel" in raw.feeds["https://datex.test/content.xml"]
    await client.aclose()


def test_proteccio_civil_normalizes_active_plan_notices() -> None:
    connector = ProteccioCivilPlansConnector(DummySession(), proteccio_civil_config())  # type: ignore[arg-type]
    raw = read_fixture("proteccio_civil_plans.json")

    connector.validate(raw)
    records = connector.normalize(raw)
    unique, duplicates = connector.deduplicate([*records, *records])

    assert len(records) == 1
    assert len(unique) == 1
    assert duplicates == 1
    assert records[0].title == "INFOCAT ALERTA"
    assert records[0].severity == "alerta"
    assert records[0].url == "https://documents.dadesobertes.gencat.cat/cecat/docs/I-124785.pdf"
