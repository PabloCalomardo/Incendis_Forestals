from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.ingestion.base import ConnectorMetrics, ValidationError
from app.ingestion.config import FirmsConnectorConfig
from app.ingestion.firms import FirmsConnector, FirmsDetection


class DummySession:
    pass


class InMemoryFirmsConnector(FirmsConnector):
    def __init__(self) -> None:
        super().__init__(DummySession(), make_config())  # type: ignore[arg-type]
        self.persisted_records: list[FirmsDetection] = []
        self.failures: list[str] = []

    async def persist(
        self,
        records: list[FirmsDetection],
        raw: str,
        started_at: datetime | None = None,
    ) -> ConnectorMetrics:
        self.persisted_records = records
        return ConnectorMetrics(received=len(records), persisted=len(records), raw_object_uri="s3://raw/firms.csv")

    async def record_failure(
        self,
        started_at: datetime,
        error: Exception,
        raw: str | None = None,
    ) -> ConnectorMetrics:
        self.failures.append(str(error))
        return ConnectorMetrics(errors=[str(error)], raw_object_uri="s3://raw/firms/dead-letter.csv")


def make_config(map_key: str = "test-key") -> FirmsConnectorConfig:
    return FirmsConnectorConfig(
        map_key=map_key,
        source="VIIRS_NOAA20_NRT",
        sources=["VIIRS_NOAA20_NRT"],
        area="-10.0,35.5,4.5,44.5",
        day_range=1,
        base_url="https://firms.modaps.eosdis.nasa.gov",
        timeout_seconds=1,
        max_retries=2,
    )


def sample_csv() -> str:
    return Path("apps/api/tests/fixtures/firms_viirs_sample.csv").read_text(encoding="utf-8")


def test_validate_rejects_missing_columns() -> None:
    connector = FirmsConnector(DummySession(), make_config())  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        connector.validate("latitude,longitude\n40,-3\n")


def test_normalize_keeps_spain_records_and_preserves_raw_fields() -> None:
    connector = FirmsConnector(DummySession(), make_config())  # type: ignore[arg-type]

    records = connector.normalize(sample_csv())

    assert len(records) == 3
    assert records[0].source == "VIIRS_NOAA20_NRT"
    assert records[0].satellite == "NOAA-20"
    assert records[0].instrument == "VIIRS"
    assert records[0].frp == 2.24
    assert records[0].raw["bright_ti4"] == "330.44"


def test_deduplicate_counts_duplicate_payload_records() -> None:
    connector = FirmsConnector(DummySession(), make_config())  # type: ignore[arg-type]
    records = connector.normalize(sample_csv())

    unique, duplicates = connector.deduplicate(records)

    assert len(unique) == 2
    assert duplicates == 1


@pytest.mark.asyncio
async def test_execute_raw_reprocesses_same_payload_idempotently() -> None:
    connector = InMemoryFirmsConnector()

    result = await connector.execute_raw(sample_csv(), started_at=datetime.now(UTC))

    assert result.status == "completed"
    assert result.metrics.received == 2
    assert result.metrics.duplicated == 1
    assert result.metrics.persisted == 2
    assert len(connector.persisted_records) == 2


@pytest.mark.asyncio
async def test_execute_raw_invalid_response_records_failure() -> None:
    connector = InMemoryFirmsConnector()

    result = await connector.execute_raw("latitude,longitude\n40,-3\n", started_at=datetime.now(UTC))

    assert result.status == "failed"
    assert connector.failures
    assert "missing required columns" in result.metrics.errors[0]


@pytest.mark.asyncio
async def test_execute_missing_map_key_returns_failed_run() -> None:
    connector = InMemoryFirmsConnector()
    connector.config = make_config(map_key="")

    result = await connector.execute()

    assert result.status == "failed"
    assert "FIRMS_MAP_KEY" in result.metrics.errors[0]


@pytest.mark.asyncio
async def test_fetch_uses_area_endpoint() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(200, text=sample_csv())

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    connector = FirmsConnector(DummySession(), make_config(), http_client=client)  # type: ignore[arg-type]

    raw = await connector.fetch()

    assert "api/area/csv/test-key/VIIRS_NOAA20_NRT/-10.0,35.5,4.5,44.5/1" in requested_urls[0]
    assert raw.startswith("firms_source,latitude,longitude")
    await client.aclose()


@pytest.mark.asyncio
async def test_fetch_merges_multiple_sources() -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        source = "VIIRS_NOAA21_NRT" if "VIIRS_NOAA21_NRT" in str(request.url) else "VIIRS_NOAA20_NRT"
        return httpx.Response(
            200,
            text=(
                "latitude,longitude,acq_date,acq_time,satellite,instrument,confidence,frp\n"
                f"40.0,-3.0,2026-07-29,1200,{source},VIIRS,n,1.2\n"
            ),
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    config = FirmsConnectorConfig(
        map_key="test-key",
        source="VIIRS_NOAA20_NRT",
        sources=["VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"],
        area="-10.0,35.5,4.5,44.5",
        day_range=1,
        base_url="https://firms.modaps.eosdis.nasa.gov",
        timeout_seconds=1,
        max_retries=2,
    )
    connector = FirmsConnector(DummySession(), config, http_client=client)  # type: ignore[arg-type]

    raw = await connector.fetch()
    records = connector.normalize(raw)

    assert len(requested_urls) == 2
    assert {record.source for record in records} == {"VIIRS_NOAA20_NRT", "VIIRS_NOAA21_NRT"}
    await client.aclose()


@pytest.mark.asyncio
async def test_fetch_requires_map_key() -> None:
    connector = FirmsConnector(DummySession(), make_config(map_key=""))  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="FIRMS_MAP_KEY"):
        await connector.fetch()


@pytest.mark.asyncio
async def test_fetch_retries_after_timeout() -> None:
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.TimeoutException("timeout")
        return httpx.Response(200, text=sample_csv())

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    connector = FirmsConnector(DummySession(), make_config(), http_client=client)  # type: ignore[arg-type]

    raw = await connector.fetch()

    assert attempts == 2
    assert "NOAA-20" in raw
    await client.aclose()
