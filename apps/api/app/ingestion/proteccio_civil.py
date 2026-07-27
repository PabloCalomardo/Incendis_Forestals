import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.enums import IngestionRunStatus, ProvenanceType, VerificationStatus
from app.domain.models import DataIngestionRun, DataSource, OfficialNotice
from app.infrastructure.object_storage import put_text_object
from app.ingestion.base import BaseConnector, ConnectorMetrics, ConnectorRunResult, ValidationError
from app.ingestion.config import ProteccioCivilConnectorConfig


@dataclass(frozen=True)
class ProteccioCivilNoticeRecord:
    external_id: str
    title: str
    body: str
    url: str | None
    severity: str | None
    observed_at: datetime | None
    original_metadata: dict[str, Any]
    deduplication_hash: str


class ProteccioCivilPlansConnector(BaseConnector[str, ProteccioCivilNoticeRecord]):
    name = "proteccio_civil_active_plans"

    def __init__(
        self,
        session: AsyncSession,
        config: ProteccioCivilConnectorConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.session = session
        self.config = config or ProteccioCivilConnectorConfig.from_settings(get_settings())
        self.http_client = http_client

    async def fetch(self) -> str:
        response = await self._request(self.config.plans_url)
        response.raise_for_status()
        return response.text

    def validate(self, raw: str) -> None:
        payload = json.loads(raw)
        if not isinstance(payload, list):
            raise ValidationError("Proteccio Civil active plans response must be a JSON array")

    def normalize(self, raw: str) -> list[ProteccioCivilNoticeRecord]:
        payload = json.loads(raw)
        records: list[ProteccioCivilNoticeRecord] = []
        for row in payload:
            if not isinstance(row, dict):
                continue
            external_id = str(row.get(":id") or self._hash("proteccio-civil", row)[:16])
            plan = self._str(row.get("plaacronim") or row.get("planom") or "Proteccio Civil") or "Proteccio Civil"
            phase = self._str(row.get("plafase"))
            active = self._str(row.get("plaactivat"))
            description = self._str(row.get("descripcio")) or ""
            title = f"{plan} {phase}".strip()[:240] if phase else plan[:240]
            url = self._nested_url(row.get("comunicatpdf"))
            body_parts = [description]
            if active:
                body_parts.append(f"Pla activat: {active}")
            if url:
                body_parts.append(f"Comunicat oficial: {url}")
            metadata = {
                "row": row,
                "plan": plan,
                "phase": phase,
                "active": active,
                "source_url": self.config.plans_url,
            }
            records.append(
                ProteccioCivilNoticeRecord(
                    external_id=external_id,
                    title=title,
                    body="\n".join(part for part in body_parts if part),
                    url=url or "https://analisi.transparenciacatalunya.cat/d/wj9c-j6vf",
                    severity=phase.lower() if phase else None,
                    observed_at=self._parse_datetime(self._str(row.get("fasedatahora"))),
                    original_metadata=metadata,
                    deduplication_hash=self._hash(external_id, metadata),
                )
            )
        return records

    def deduplicate(self, records: list[ProteccioCivilNoticeRecord]) -> tuple[list[ProteccioCivilNoticeRecord], int]:
        seen: set[str] = set()
        unique: list[ProteccioCivilNoticeRecord] = []
        duplicates = 0
        for record in records:
            if record.deduplication_hash in seen:
                duplicates += 1
                continue
            seen.add(record.deduplication_hash)
            unique.append(record)
        return unique, duplicates

    async def persist(self, records: list[ProteccioCivilNoticeRecord], raw: str) -> ConnectorMetrics:
        started_at = datetime.now(UTC)
        source = await self._get_or_create_source()
        raw_uri = await asyncio.to_thread(
            put_text_object,
            f"proteccio-civil/plans/{started_at:%Y/%m/%d/%H%M%S}.json",
            raw,
            "application/json",
        )
        run = DataIngestionRun(
            source_id=source.id,
            connector_name=self.name,
            status=IngestionRunStatus.STARTED,
            started_at=started_at,
            raw_object_uri=raw_uri,
        )
        self.session.add(run)
        await self.session.flush()
        existing = await self._existing_hashes([record.deduplication_hash for record in records])
        persisted = 0
        duplicates = 0
        for record in records:
            if record.deduplication_hash in existing:
                duplicates += 1
                continue
            self.session.add(
                OfficialNotice(
                    source_id=source.id,
                    external_id=record.external_id,
                    provenance=ProvenanceType.OFFICIAL,
                    observed_at=record.observed_at,
                    published_at=record.observed_at,
                    received_at=started_at,
                    verification_status=VerificationStatus.PENDING,
                    confidence=0.95,
                    original_metadata=record.original_metadata,
                    deduplication_hash=record.deduplication_hash,
                    title=record.title,
                    body=record.body,
                    url=record.url,
                    severity=record.severity,
                )
            )
            persisted += 1
        run.status = IngestionRunStatus.COMPLETED
        run.finished_at = datetime.now(UTC)
        run.received_count = len(records)
        run.duplicate_count = duplicates
        run.persisted_count = persisted
        run.metrics = {"url": self.config.plans_url}
        await self.session.commit()
        return ConnectorMetrics(received=len(records), duplicated=duplicates, persisted=persisted, raw_object_uri=raw_uri)

    async def report_metrics(self, metrics: ConnectorMetrics) -> None:
        return None

    async def execute(self) -> ConnectorRunResult:
        started_at = datetime.now(UTC)
        raw: str | None = None
        try:
            raw = await self.fetch()
            self.validate(raw)
            unique, payload_duplicates = self.deduplicate(self.normalize(raw))
            metrics = await self.persist(unique, raw)
            metrics.duplicated += payload_duplicates
            return ConnectorRunResult(self.name, "completed", started_at, datetime.now(UTC), metrics)
        except Exception as exc:
            await self.session.rollback()
            metrics = await self.record_failure(started_at, exc, raw)
            return ConnectorRunResult(self.name, "failed", started_at, datetime.now(UTC), metrics)

    async def record_failure(self, started_at: datetime, error: Exception, raw: str | None = None) -> ConnectorMetrics:
        raw_uri = None
        if raw:
            raw_uri = await asyncio.to_thread(
                put_text_object,
                f"proteccio-civil/dead-letter/{started_at:%Y/%m/%d/%H%M%S}.json",
                raw,
                "application/json",
            )
        source = await self._get_or_create_source()
        self.session.add(
            DataIngestionRun(
                source_id=source.id,
                connector_name=self.name,
                status=IngestionRunStatus.FAILED,
                started_at=started_at,
                finished_at=datetime.now(UTC),
                raw_object_uri=raw_uri,
                error_summary={"error": str(error), "type": error.__class__.__name__},
            )
        )
        await self.session.commit()
        return ConnectorMetrics(errors=[str(error)], raw_object_uri=raw_uri)

    async def _request(self, url: str) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                if self.http_client is not None:
                    return await self.http_client.get(url, timeout=self.config.timeout_seconds)
                async with httpx.AsyncClient() as client:
                    return await client.get(url, timeout=self.config.timeout_seconds)
            except (httpx.TimeoutException, httpx.HTTPError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
        raise ValidationError(f"Proteccio Civil fetch failed: {last_error}")

    async def _get_or_create_source(self) -> DataSource:
        result = await self.session.execute(select(DataSource).where(DataSource.name == "Proteccio Civil active plans"))
        source = result.scalar_one_or_none()
        if source is not None:
            return source
        source = DataSource(
            name="Proteccio Civil active plans",
            source_type=ProvenanceType.OFFICIAL,
            authority="Generalitat de Catalunya / Proteccio Civil / CECAT",
            base_url=self.config.plans_url,
            license_name="Generalitat de Catalunya open data licence",
            attribution="Proteccio Civil de Catalunya / CECAT",
            update_frequency="as published by open data portal",
            reliability_score=0.95,
            source_metadata={"dataset": "wj9c-j6vf"},
        )
        self.session.add(source)
        await self.session.flush()
        return source

    async def _existing_hashes(self, hashes: list[str]) -> set[str]:
        if not hashes:
            return set()
        result = await self.session.execute(select(OfficialNotice.deduplication_hash).where(OfficialNotice.deduplication_hash.in_(hashes)))
        return {item for item in result.scalars() if item is not None}

    def _nested_url(self, value: Any) -> str | None:
        if isinstance(value, dict):
            return self._str(value.get("url"))
        return None

    def _str(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if value is None:
            return None
        for pattern in ("%d/%m/%Y %H:%M", "%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"):
            try:
                parsed = datetime.strptime(value, pattern)
                return parsed.replace(tzinfo=UTC)
            except ValueError:
                continue
        return None

    def _hash(self, external_id: str, payload: dict[str, Any]) -> str:
        stable = f"{external_id}|{json.dumps(payload, sort_keys=True, default=str)}"
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()
