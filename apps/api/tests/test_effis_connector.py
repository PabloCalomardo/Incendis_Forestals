import io
import zipfile
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import shapefile

from app.ingestion.base import ValidationError
from app.ingestion.config import EffisConnectorConfig
from app.ingestion.effis import EffisBurntAreasConnector


class DummySession:
    pass


def make_config() -> EffisConnectorConfig:
    return EffisConnectorConfig(
        wfs_url="https://maps.effis.emergency.copernicus.eu/effis",
        type_name="ms:modis.ba.poly",
        area_bbox="-10.0,35.5,4.5,44.5",
        timeout_seconds=1,
        max_retries=2,
    )


def shapefile_zip(days_ago: int = 1, outside_bbox: bool = False) -> bytes:
    shp = io.BytesIO()
    shx = io.BytesIO()
    dbf = io.BytesIO()
    writer = shapefile.Writer(shp=shp, shx=shx, dbf=dbf, shapeType=shapefile.POLYGON)
    writer.field("ID", "C", size=20)
    writer.field("FIREDATE", "C", size=20)
    writer.field("FINALDATE", "C", size=20)
    writer.field("LASTUPDATE", "C", size=20)
    writer.field("COUNTRY", "C", size=30)
    writer.field("PROVINCE", "C", size=30)
    writer.field("COMMUNE", "C", size=30)
    writer.field("AREA_HA", "N", size=12, decimal=2)
    writer.field("CONIFER", "N", size=6, decimal=2)
    writer.field("CLASS", "C", size=20)
    day = (datetime.now(UTC) - timedelta(days=days_ago)).date().isoformat()
    west = 20.0 if outside_bbox else -3.8
    polygon = [[west, 40.3], [west, 40.4], [west + 0.1, 40.4], [west + 0.1, 40.3], [west, 40.3]]
    writer.poly([polygon])
    writer.record("area-1", day, day, day, "Spain", "Madrid", "Robledo", 12.5, 68.0, "Forest")
    writer.close()
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w") as archive:
        archive.writestr("effis.shp", shp.getvalue())
        archive.writestr("effis.shx", shx.getvalue())
        archive.writestr("effis.dbf", dbf.getvalue())
    return archive_buffer.getvalue()


def test_normalize_maps_polygon_and_preserves_all_dbf_attributes() -> None:
    connector = EffisBurntAreasConnector(DummySession(), make_config())  # type: ignore[arg-type]

    records = connector.normalize(shapefile_zip())

    assert len(records) == 1
    assert records[0].geometry_wkt.startswith("POLYGON((")
    assert records[0].area_hectares == 12.5
    assert records[0].province == "Madrid"
    assert records[0].metadata["operational_extinction_status_available"] is False
    attributes = records[0].metadata["shapefile_attributes"]
    assert isinstance(attributes, dict)
    assert attributes["CONIFER"] == 68.0
    assert attributes["CLASS"] == "Forest"


def test_normalize_keeps_historic_areas_and_filters_outside_bbox() -> None:
    connector = EffisBurntAreasConnector(DummySession(), make_config())  # type: ignore[arg-type]

    historic = connector.normalize(shapefile_zip(days_ago=800))
    outside = connector.normalize(shapefile_zip(outside_bbox=True))

    assert len(historic) == 1
    assert outside == []


def test_validate_rejects_non_zip_response() -> None:
    connector = EffisBurntAreasConnector(DummySession(), make_config())  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="SHAPEZIP"):
        connector.validate(b"not-a-zip")


@pytest.mark.asyncio
async def test_fetch_requests_official_shapefile_download() -> None:
    request: httpx.Request | None = None

    def handler(incoming: httpx.Request) -> httpx.Response:
        nonlocal request
        request = incoming
        return httpx.Response(200, content=shapefile_zip())

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    connector = EffisBurntAreasConnector(DummySession(), make_config(), client)  # type: ignore[arg-type]

    raw = await connector.fetch()

    assert request is not None
    assert request.url.params["typeName"] == "ms:modis.ba.poly"
    assert request.url.params["outputFormat"] == "SHAPEZIP"
    assert raw.startswith(b"PK")
    await client.aclose()


@pytest.mark.asyncio
async def test_fetch_retries_after_timeout() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.TimeoutException("timeout")
        return httpx.Response(200, content=shapefile_zip())

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    connector = EffisBurntAreasConnector(DummySession(), make_config(), client)  # type: ignore[arg-type]

    assert (await connector.fetch()).startswith(b"PK")
    assert attempts == 2
    await client.aclose()
