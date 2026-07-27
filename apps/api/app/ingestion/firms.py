import asyncio
import csv
import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO

import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.enums import IngestionRunStatus, ProvenanceType, VerificationStatus
from app.domain.models import DataIngestionRun, DataSource, FireDetection
from app.infrastructure.object_storage import put_text_object
from app.ingestion.base import BaseConnector, ConnectorMetrics, ConnectorRunResult, ValidationError
from app.ingestion.config import FirmsConnectorConfig

SPAIN_BBOX = (-10.0, 35.5, 4.5, 44.5)


@dataclass(frozen=True)
class FirmsDetection:
    latitude: float
    longitude: float
    acq_date: str
    acq_time: str
    satellite: str
    instrument: str
    confidence: str
    frp: float | None
    raw: dict[str, str]
    deduplication_hash: str

    @property
    def observed_at(self) -> datetime:
        padded_time = self.acq_time.zfill(4)
        return datetime.strptime(
            f"{self.acq_date} {padded_time}",
            "%Y-%m-%d %H%M",
        ).replace(tzinfo=UTC)


class FirmsConnector(BaseConnector[str, FirmsDetection]):
    name = "nasa_firms"

    def __init__(
        self,
        session: AsyncSession,
        config: FirmsConnectorConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.session = session
        self.config = config or FirmsConnectorConfig.from_settings(get_settings())
        self.http_client = http_client

    async def fetch(self) -> str:
        if not self.config.map_key:
            raise ValidationError("FIRMS_MAP_KEY is required to execute NASA FIRMS connector")

        url = (
            f"{self.config.base_url}/api/area/csv/{self.config.map_key}/"
            f"{self.config.source}/{self.config.area}/{self.config.day_range}"
        )
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                if self.http_client is not None:
                    response = await self.http_client.get(url, timeout=self.config.timeout_seconds)
                else:
                    async with httpx.AsyncClient() as client:
                        response = await client.get(url, timeout=self.config.timeout_seconds)
                response.raise_for_status()
                return response.text
            except (httpx.TimeoutException, httpx.HTTPError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
        raise ValidationError(f"NASA FIRMS fetch failed: {last_error}")

    def validate(self, raw: str) -> None:
        if not raw.strip():
            raise ValidationError("NASA FIRMS response is empty")
        reader = csv.DictReader(StringIO(raw))
        required = {"latitude", "longitude", "acq_date", "acq_time", "satellite", "confidence", "frp"}
        if reader.fieldnames is None or not required.issubset(set(reader.fieldnames)):
            raise ValidationError(f"NASA FIRMS response missing required columns: {sorted(required)}")

    def normalize(self, raw: str) -> list[FirmsDetection]:
        reader = csv.DictReader(StringIO(raw))
        records: list[FirmsDetection] = []
        for row in reader:
            try:
                latitude = float(row["latitude"])
                longitude = float(row["longitude"])
            except (KeyError, ValueError):
                continue
            if not self._inside_spain_bbox(longitude, latitude):
                continue
            deduplication_hash = self._deduplication_hash(row)
            records.append(
                FirmsDetection(
                    latitude=latitude,
                    longitude=longitude,
                    acq_date=row["acq_date"],
                    acq_time=row["acq_time"],
                    satellite=row.get("satellite", ""),
                    instrument=row.get("instrument", self.config.source),
                    confidence=row.get("confidence", ""),
                    frp=self._optional_float(row.get("frp")),
                    raw=dict(row),
                    deduplication_hash=deduplication_hash,
                )
            )
        return records

    def deduplicate(self, records: list[FirmsDetection]) -> tuple[list[FirmsDetection], int]:
        seen: set[str] = set()
        unique: list[FirmsDetection] = []
        duplicates = 0
        for record in records:
            if record.deduplication_hash in seen:
                duplicates += 1
                continue
            seen.add(record.deduplication_hash)
            unique.append(record)
        return unique, duplicates

    async def persist(self, records: list[FirmsDetection], raw: str, started_at: datetime | None = None) -> ConnectorMetrics:
        now = started_at or datetime.now(UTC)
        source = await self._get_or_create_source()
        raw_uri = await asyncio.to_thread(
            put_text_object,
            f"firms/{now:%Y/%m/%d/%H%M%S}.csv",
            raw,
            "text/csv",
        )
        run = DataIngestionRun(
            source_id=source.id,
            connector_name=self.name,
            status=IngestionRunStatus.STARTED,
            started_at=now,
            raw_object_uri=raw_uri,
        )
        self.session.add(run)
        await self.session.flush()

        existing_hashes = await self._existing_hashes([record.deduplication_hash for record in records])
        persisted = 0
        duplicate_count = 0
        for record in records:
            if record.deduplication_hash in existing_hashes:
                duplicate_count += 1
                continue
            self.session.add(
                FireDetection(
                    source_id=source.id,
                    external_id=record.deduplication_hash,
                    provenance=ProvenanceType.OBSERVED,
                    observed_at=record.observed_at,
                    published_at=None,
                    received_at=now,
                    verification_status=VerificationStatus.PENDING,
                    confidence=self._confidence_to_score(record.confidence),
                    original_metadata=record.raw,
                    deduplication_hash=record.deduplication_hash,
                    geometry=WKTElement(f"POINT({record.longitude} {record.latitude})", srid=4326),
                    original_crs="EPSG:4326",
                    sensor=record.instrument,
                    satellite=record.satellite,
                    latitude=record.latitude,
                    longitude=record.longitude,
                    frp_mw=record.frp,
                )
            )
            persisted += 1

        run.status = IngestionRunStatus.COMPLETED
        run.finished_at = datetime.now(UTC)
        run.received_count = len(records)
        run.duplicate_count = duplicate_count
        run.persisted_count = persisted
        run.discarded_count = 0
        run.metrics = {"source": self.config.source, "area": self.config.area}
        await self.session.commit()
        return ConnectorMetrics(
            received=len(records),
            duplicated=duplicate_count,
            persisted=persisted,
            raw_object_uri=raw_uri,
        )

    async def record_failure(
        self,
        started_at: datetime,
        error: Exception,
        raw: str | None = None,
    ) -> ConnectorMetrics:
        raw_uri = None
        if raw:
            raw_uri = await asyncio.to_thread(
                put_text_object,
                f"firms/dead-letter/{started_at:%Y/%m/%d/%H%M%S}.csv",
                raw,
                "text/csv",
            )
        source = await self._get_or_create_source()
        run = DataIngestionRun(
            source_id=source.id,
            connector_name=self.name,
            status=IngestionRunStatus.FAILED,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            raw_object_uri=raw_uri,
            error_summary={"error": str(error), "type": error.__class__.__name__},
            metrics={"source": self.config.source, "area": self.config.area},
        )
        self.session.add(run)
        await self.session.commit()
        return ConnectorMetrics(errors=[str(error)], raw_object_uri=raw_uri)

    async def report_metrics(self, metrics: ConnectorMetrics) -> None:
        return None

    async def execute(self) -> ConnectorRunResult:
        started_at = datetime.now(UTC)
        raw: str | None = None
        try:
            raw = await self.fetch()
            return await self.execute_raw(raw, started_at=started_at)
        except Exception as exc:
            metrics = await self.record_failure(started_at, exc, raw=raw)
            await self.report_metrics(metrics)
            return ConnectorRunResult(
                connector_name=self.name,
                status="failed",
                started_at=started_at,
                finished_at=datetime.now(UTC),
                metrics=metrics,
            )

    async def execute_raw(self, raw: str, started_at: datetime | None = None) -> ConnectorRunResult:
        run_started_at = started_at or datetime.now(UTC)
        try:
            self.validate(raw)
            normalized = self.normalize(raw)
            unique, in_payload_duplicates = self.deduplicate(normalized)
            metrics = await self.persist(unique, raw, started_at=run_started_at)
            metrics.duplicated += in_payload_duplicates
            await self.report_metrics(metrics)
            return ConnectorRunResult(
                connector_name=self.name,
                status="completed",
                started_at=run_started_at,
                finished_at=datetime.now(UTC),
                metrics=metrics,
            )
        except Exception as exc:
            metrics = await self.record_failure(run_started_at, exc, raw=raw)
            await self.report_metrics(metrics)
            return ConnectorRunResult(
                connector_name=self.name,
                status="failed",
                started_at=run_started_at,
                finished_at=datetime.now(UTC),
                metrics=metrics,
            )

    async def _get_or_create_source(self) -> DataSource:
        result = await self.session.execute(select(DataSource).where(DataSource.name == "NASA FIRMS"))
        source = result.scalar_one_or_none()
        if source is not None:
            return source
        source = DataSource(
            name="NASA FIRMS",
            source_type=ProvenanceType.OBSERVED,
            authority="NASA LANCE FIRMS",
            base_url=self.config.base_url,
            license_name="NASA FIRMS terms",
            attribution="NASA FIRMS",
            update_frequency="near-real-time",
            reliability_score=0.8,
            source_metadata={"source": self.config.source},
        )
        self.session.add(source)
        await self.session.flush()
        return source

    async def _existing_hashes(self, hashes: list[str]) -> set[str]:
        if not hashes:
            return set()
        result = await self.session.execute(
            select(FireDetection.deduplication_hash).where(FireDetection.deduplication_hash.in_(hashes))
        )
        return {hash_value for hash_value in result.scalars() if hash_value is not None}

    def _deduplication_hash(self, row: dict[str, str]) -> str:
        stable = "|".join(
            [
                self.config.source,
                row.get("satellite", ""),
                row.get("instrument", ""),
                row.get("latitude", ""),
                row.get("longitude", ""),
                row.get("acq_date", ""),
                row.get("acq_time", ""),
            ]
        )
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()

    def _inside_spain_bbox(self, longitude: float, latitude: float) -> bool:
        west, south, east, north = SPAIN_BBOX
        return west <= longitude <= east and south <= latitude <= north

    def _optional_float(self, value: str | None) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except ValueError:
            return None

    def _confidence_to_score(self, confidence: str) -> float | None:
        mapping = {"l": 0.4, "n": 0.6, "h": 0.85}
        if confidence.lower() in mapping:
            return mapping[confidence.lower()]
        try:
            value = float(confidence)
        except ValueError:
            return None
        return max(0.0, min(value / 100.0, 1.0))
