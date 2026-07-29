import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.enums import IngestionRunStatus, ProvenanceType, VerificationStatus
from app.domain.models import DataIngestionRun, DataSource, OfficialNotice
from app.infrastructure.object_storage import put_text_object
from app.ingestion.base import BaseConnector, ConnectorMetrics, ConnectorRunResult, ValidationError
from app.ingestion.config import AemetAlertsConnectorConfig

CAP_NAMESPACE = {"cap": "urn:oasis:names:tc:emergency:cap:1.2"}


@dataclass(frozen=True)
class AemetAlertRecord:
    external_id: str
    title: str
    body: str
    url: str
    severity: str | None
    observed_at: datetime | None
    original_metadata: dict[str, Any]
    deduplication_hash: str


class AemetAlertsConnector(BaseConnector[str, AemetAlertRecord]):
    name = "aemet_cap_alerts"

    def __init__(
        self,
        session: AsyncSession,
        config: AemetAlertsConnectorConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.session = session
        self.config = config or AemetAlertsConnectorConfig.from_settings(get_settings())
        self.http_client = http_client

    async def fetch(self) -> str:
        feed_response = await self._request(self.config.feed_url)
        feed_response.raise_for_status()
        links = self._feed_links(feed_response.text)
        semaphore = asyncio.Semaphore(12)

        async def fetch_cap(url: str) -> dict[str, str]:
            async with semaphore:
                response = await self._request(url)
                response.raise_for_status()
                return {"url": url, "xml": response.text}

        messages = await asyncio.gather(*(fetch_cap(url) for url in links))
        return json.dumps({"feed_url": self.config.feed_url, "messages": messages}, ensure_ascii=False)

    def validate(self, raw: str) -> None:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("messages"), list):
            raise ValidationError("AEMET CAP payload must contain a messages array")
        if not payload["messages"]:
            raise ValidationError("AEMET CAP feed returned no active alert messages")
        for message in payload["messages"]:
            if not isinstance(message, dict) or not isinstance(message.get("xml"), str):
                raise ValidationError("AEMET CAP message is invalid")
            ElementTree.fromstring(message["xml"])

    def normalize(self, raw: str) -> list[AemetAlertRecord]:
        payload = json.loads(raw)
        records: list[AemetAlertRecord] = []
        for message in payload["messages"]:
            root = ElementTree.fromstring(message["xml"])
            info = self._spanish_info(root)
            if info is None:
                continue
            identifier = self._text(root, "cap:identifier")
            if not identifier:
                continue
            level = self._warning_level(info)
            area = info.find("cap:area", CAP_NAMESPACE)
            area_name = self._text(area, "cap:areaDesc") if area is not None else None
            polygon = self._text(area, "cap:polygon") if area is not None else None
            headline = self._text(info, "cap:headline") or self._text(info, "cap:event") or "Avís AEMET"
            description = self._text(info, "cap:description") or ""
            instruction = self._text(info, "cap:instruction")
            onset = self._text(info, "cap:onset")
            expires = self._text(info, "cap:expires")
            metadata = {
                "provider": "AEMET",
                "alert_level": level,
                "area": area_name,
                "area_bbox": self._polygon_bbox(polygon),
                "polygon": polygon,
                "onset": onset,
                "expires": expires,
                "event": self._text(info, "cap:event"),
                "urgency": self._text(info, "cap:urgency"),
                "certainty": self._text(info, "cap:certainty"),
                "cap_severity": self._text(info, "cap:severity"),
                "feed_url": self.config.feed_url,
                "cap_url": message["url"],
            }
            body = "\n".join(part for part in (description, instruction) if part)
            records.append(
                AemetAlertRecord(
                    external_id=identifier,
                    title=headline[:240],
                    body=body,
                    url=self._text(info, "cap:web") or message["url"],
                    severity=level,
                    observed_at=self._parse_datetime(self._text(root, "cap:sent")),
                    original_metadata=metadata,
                    deduplication_hash=self._hash(identifier, metadata),
                )
            )
        return records

    def deduplicate(self, records: list[AemetAlertRecord]) -> tuple[list[AemetAlertRecord], int]:
        unique = {record.deduplication_hash: record for record in records}
        return list(unique.values()), len(records) - len(unique)

    async def persist(self, records: list[AemetAlertRecord], raw: str) -> ConnectorMetrics:
        started_at = datetime.now(UTC)
        source = await self._get_or_create_source()
        raw_uri = await asyncio.to_thread(
            put_text_object,
            f"aemet/alerts/{started_at:%Y/%m/%d/%H%M%S}.json",
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
        for record in records:
            if record.deduplication_hash in existing:
                continue
            self.session.add(
                OfficialNotice(
                    source_id=source.id,
                    external_id=record.external_id,
                    provenance=ProvenanceType.OFFICIAL,
                    observed_at=record.observed_at,
                    published_at=record.observed_at,
                    received_at=started_at,
                    verification_status=VerificationStatus.VERIFIED,
                    confidence=0.99,
                    original_metadata=record.original_metadata,
                    deduplication_hash=record.deduplication_hash,
                    title=record.title,
                    body=record.body,
                    url=record.url,
                    severity=record.severity,
                )
            )
            persisted += 1
        duplicates = len(records) - persisted
        run.status = IngestionRunStatus.COMPLETED
        run.finished_at = datetime.now(UTC)
        run.received_count = len(records)
        run.duplicate_count = duplicates
        run.persisted_count = persisted
        run.metrics = {"url": self.config.feed_url}
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
                f"aemet/alerts/dead-letter/{started_at:%Y/%m/%d/%H%M%S}.json",
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
        raise ValidationError(f"AEMET alerts fetch failed: {last_error}")

    async def _get_or_create_source(self) -> DataSource:
        result = await self.session.execute(select(DataSource).where(DataSource.name == "AEMET Meteoalerta"))
        source = result.scalar_one_or_none()
        if source is not None:
            return source
        source = DataSource(
            name="AEMET Meteoalerta",
            source_type=ProvenanceType.OFFICIAL,
            authority="Agencia Estatal de Meteorologia / Gobierno de Espana",
            base_url=self.config.feed_url,
            license_name="AEMET reuse terms",
            attribution="AEMET",
            update_frequency="continuous",
            reliability_score=0.99,
            source_metadata={"format": "CAP 1.2", "coverage": "Spain"},
        )
        self.session.add(source)
        await self.session.flush()
        return source

    async def _existing_hashes(self, hashes: list[str]) -> set[str]:
        if not hashes:
            return set()
        result = await self.session.execute(
            select(OfficialNotice.deduplication_hash).where(OfficialNotice.deduplication_hash.in_(hashes))
        )
        return {item for item in result.scalars() if item is not None}

    def _feed_links(self, raw: str) -> list[str]:
        root = ElementTree.fromstring(raw)
        links: list[str] = []
        for item in root.findall("./channel/item"):
            link = self._text(item, "link")
            if link and link.lower().endswith(".xml"):
                links.append(link)
        return list(dict.fromkeys(links))

    def _spanish_info(self, root: ElementTree.Element) -> ElementTree.Element | None:
        infos = root.findall("cap:info", CAP_NAMESPACE)
        return next(
            (info for info in infos if (self._text(info, "cap:language") or "").lower().startswith("es")),
            infos[0] if infos else None,
        )

    def _warning_level(self, info: ElementTree.Element) -> str | None:
        for parameter in info.findall("cap:parameter", CAP_NAMESPACE):
            if "nivel" in (self._text(parameter, "cap:valueName") or "").lower():
                return self._normalize_level(self._text(parameter, "cap:value"))
        return {"Moderate": "yellow", "Severe": "orange", "Extreme": "red"}.get(
            self._text(info, "cap:severity") or ""
        )

    def _normalize_level(self, value: str | None) -> str | None:
        normalized = (value or "").strip().lower()
        return {
            "amarillo": "yellow",
            "yellow": "yellow",
            "naranja": "orange",
            "orange": "orange",
            "rojo": "red",
            "red": "red",
        }.get(normalized)

    def _polygon_bbox(self, polygon: str | None) -> str | None:
        if not polygon:
            return None
        coordinates: list[tuple[float, float]] = []
        try:
            for pair in polygon.split():
                latitude, longitude = (float(value) for value in pair.split(",", 1))
                coordinates.append((longitude, latitude))
        except ValueError:
            return None
        if not coordinates:
            return None
        longitudes, latitudes = zip(*coordinates, strict=True)
        return f"{min(longitudes):.6f},{min(latitudes):.6f},{max(longitudes):.6f},{max(latitudes):.6f}"

    def _text(self, root: ElementTree.Element | None, path: str) -> str | None:
        if root is None:
            return None
        node = root.find(path, CAP_NAMESPACE)
        if node is None or node.text is None:
            return None
        return node.text.strip() or None

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return parsed.astimezone(UTC)
        except ValueError:
            return None

    def _hash(self, external_id: str, payload: dict[str, Any]) -> str:
        stable = f"{external_id}|{json.dumps(payload, sort_keys=True, default=str)}"
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()
