import asyncio
import base64
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.enums import IngestionRunStatus, ProvenanceType, RoadIncidentKind, VerificationStatus, ZoneKind
from app.domain.models import DataIngestionRun, DataSource, RestrictionZone, RoadIncident, RoadSegment
from app.infrastructure.object_storage import put_text_object
from app.ingestion.base import BaseConnector, ConnectorMetrics, ConnectorRunResult, ValidationError
from app.ingestion.config import EtrafficConnectorConfig
from app.ingestion.locks import try_acquire_traffic_ingestion_lock
from app.ingestion.spatial import linestring_wkt

ETRAFFIC_DECODER_KEY = ord("f")
SUPPORTED_GEOMETRY_TYPES = {"LineString", "MultiLineString"}


@dataclass(frozen=True)
class EtrafficRecord:
    external_id: str
    title: str
    road_ref: str | None
    kind: str
    geometry_wkt: str
    segment_wkts: list[str]
    observed_at: datetime | None
    original_metadata: dict[str, Any]
    deduplication_hash: str


class DgtEtrafficConnector(BaseConnector[str, EtrafficRecord]):
    name = "dgt_etraffic_restrictions"

    def __init__(
        self,
        session: AsyncSession,
        config: EtrafficConnectorConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.session = session
        self.config = config or EtrafficConnectorConfig.from_settings(get_settings())
        self.http_client = http_client

    async def fetch(self) -> str:
        if not self.config.filters_via:
            raise ValidationError("ETRAFFIC_FILTERS_VIA is empty")
        response = await self._request(
            f"{self.config.base_url}/cache/getFilteredData",
            {"filtrosVia": self.config.filters_via},
        )
        response.raise_for_status()
        return self._decode_response(response.text)

    def validate(self, raw: str) -> None:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("situationsRecords"), list):
            raise ValidationError("DGT eTraffic response must contain situationsRecords array")

    def normalize(self, raw: str) -> list[EtrafficRecord]:
        payload = json.loads(raw)
        records: list[EtrafficRecord] = []
        for item in payload.get("situationsRecords", []):
            if not isinstance(item, dict):
                continue
            geometry = self._geometry(item.get("geometria"))
            if geometry is None or geometry.get("type") not in SUPPORTED_GEOMETRY_TYPES:
                continue
            geometry_wkt = self._geometry_wkt(geometry)
            segment_wkts = self._segment_wkts(geometry)
            if geometry_wkt is None or not segment_wkts:
                continue
            external_id = f"etraffic:{self._str(item.get('id')) or self._hash('item', item)[:16]}"
            road_ref = self._str(item.get("carretera"))
            kind = self._str(item.get("tipoVialidad")) or self._str(item.get("causa")) or "etraffic"
            title = self._title(item, kind, road_ref)
            metadata = {
                "source": "DGT eTraffic",
                "raw": item,
                "geometry_type": geometry.get("type"),
                "road_ref": road_ref,
                "kind": kind,
                "cause": self._str(item.get("causa")),
                "subcause": self._str(item.get("subcausa")),
                "source_authority": self._str(item.get("fuente")),
            }
            records.append(
                EtrafficRecord(
                    external_id=external_id,
                    title=title,
                    road_ref=road_ref,
                    kind=kind,
                    geometry_wkt=geometry_wkt,
                    segment_wkts=segment_wkts,
                    observed_at=self._parse_datetime(self._str(item.get("fechaInicio"))),
                    original_metadata=metadata,
                    deduplication_hash=self._hash(external_id, metadata),
                )
            )
        return records

    def deduplicate(self, records: list[EtrafficRecord]) -> tuple[list[EtrafficRecord], int]:
        seen: set[str] = set()
        unique: list[EtrafficRecord] = []
        duplicates = 0
        for record in records:
            if record.deduplication_hash in seen:
                duplicates += 1
                continue
            seen.add(record.deduplication_hash)
            unique.append(record)
        return unique, duplicates

    async def persist(self, records: list[EtrafficRecord], raw: str) -> ConnectorMetrics:
        started_at = datetime.now(UTC)
        source = await self._get_or_create_source()
        raw_uri = await asyncio.to_thread(
            put_text_object,
            f"etraffic/restrictions/{started_at:%Y/%m/%d/%H%M%S}.json",
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
        await self._expire_fallback_datex(started_at)
        current_hashes = [record.deduplication_hash for record in records]
        await self._expire_stale_source_records(source.id, current_hashes, started_at)
        existing = await self._existing_hashes(current_hashes)
        persisted = 0
        duplicates = 0
        for record in records:
            if record.deduplication_hash in existing:
                duplicates += 1
                await self._reactivate_existing(record.deduplication_hash)
                continue
            first_segment = await self._persist_segments(record, source.id, started_at)
            if first_segment is None:
                continue
            self.session.add(
                RoadIncident(
                    source_id=source.id,
                    external_id=f"{record.external_id}:incident",
                    provenance=ProvenanceType.OFFICIAL,
                    observed_at=record.observed_at,
                    received_at=started_at,
                    verification_status=VerificationStatus.PENDING,
                    confidence=0.96,
                    original_metadata=record.original_metadata,
                    deduplication_hash=f"etraffic:incident:{record.deduplication_hash}",
                    road_segment_id=first_segment.id,
                    kind=self._road_incident_kind(record.kind),
                    explanation=record.title,
                )
            )
            self.session.add(
                RestrictionZone(
                    source_id=source.id,
                    external_id=f"{record.external_id}:restriction",
                    provenance=ProvenanceType.OFFICIAL,
                    observed_at=record.observed_at,
                    received_at=started_at,
                    verification_status=VerificationStatus.PENDING,
                    confidence=0.96,
                    original_metadata=record.original_metadata,
                    deduplication_hash=f"etraffic:restriction:{record.deduplication_hash}",
                    geometry=WKTElement(record.geometry_wkt, srid=4326),
                    original_crs="EPSG:4326",
                    name=record.title[:180],
                    zone_kind=ZoneKind.RESTRICTION,
                    restriction_type=record.kind[:120],
                )
            )
            persisted += 1
        run.status = IngestionRunStatus.COMPLETED
        run.finished_at = datetime.now(UTC)
        run.received_count = len(records)
        run.duplicate_count = duplicates
        run.persisted_count = persisted
        run.metrics = {"base_url": self.config.base_url, "filters_via": self.config.filters_via}
        await self.session.commit()
        return ConnectorMetrics(received=len(records), duplicated=duplicates, persisted=persisted, raw_object_uri=raw_uri)

    async def report_metrics(self, metrics: ConnectorMetrics) -> None:
        return None

    async def execute(self) -> ConnectorRunResult:
        started_at = datetime.now(UTC)
        raw: str | None = None
        try:
            if not await try_acquire_traffic_ingestion_lock(self.session):
                return ConnectorRunResult(
                    self.name,
                    "skipped_locked",
                    started_at,
                    datetime.now(UTC),
                    ConnectorMetrics(errors=["Another traffic ingestion is already running"]),
                )
            raw = await self.fetch()
            self.validate(raw)
            unique, payload_duplicates = self.deduplicate(self.normalize(raw))
            if not unique:
                raise ValidationError("DGT eTraffic normalization produced no traffic restrictions")
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
                f"etraffic/dead-letter/{started_at:%Y/%m/%d/%H%M%S}.json",
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

    async def _request(self, url: str, body: dict[str, Any]) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                if self.http_client is not None:
                    return await self.http_client.post(url, json=body, timeout=self.config.timeout_seconds)
                async with httpx.AsyncClient() as client:
                    return await client.post(url, json=body, timeout=self.config.timeout_seconds)
            except (httpx.TimeoutException, httpx.HTTPError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
        raise ValidationError(f"DGT eTraffic fetch failed: {last_error}")

    async def _get_or_create_source(self) -> DataSource:
        result = await self.session.execute(select(DataSource).where(DataSource.name == "NAP Mapa de Trafico"))
        source = result.scalar_one_or_none()
        metadata: dict[str, object] = {
            "nap_dataset": "Mapa de Trafico",
            "public_url": self.config.public_url,
            "endpoint": "/cache/getFilteredData",
            "filters_via": self.config.filters_via,
        }
        if source is not None:
            source.base_url = self.config.base_url
            source.source_metadata = metadata
            return source
        source = DataSource(
            name="NAP Mapa de Trafico",
            source_type=ProvenanceType.OFFICIAL,
            authority="Direccion General de Trafico",
            base_url=self.config.base_url,
            license_name="NAP Mapa de Trafico / DGT legal notice",
            attribution="DGT NAP - Mapa de Trafico",
            update_frequency="1 minute according to NAP dataset metadata",
            expected_delay_seconds=300,
            reliability_score=0.96,
            source_metadata=metadata,
        )
        self.session.add(source)
        await self.session.flush()
        return source

    async def _persist_segments(
        self,
        record: EtrafficRecord,
        source_id: Any,
        started_at: datetime,
    ) -> RoadSegment | None:
        first_segment: RoadSegment | None = None
        for index, segment_wkt in enumerate(record.segment_wkts):
            segment = RoadSegment(
                source_id=source_id,
                external_id=f"{record.external_id}:segment:{index}",
                provenance=ProvenanceType.OFFICIAL,
                observed_at=record.observed_at,
                received_at=started_at,
                verification_status=VerificationStatus.PENDING,
                confidence=0.96,
                original_metadata={**record.original_metadata, "segment_index": index},
                deduplication_hash=f"etraffic:segment:{record.deduplication_hash}:{index}",
                geometry=WKTElement(segment_wkt, srid=4326),
                original_crs="EPSG:4326",
                name=record.title[:160],
                road_ref=record.road_ref,
                road_class="etraffic_affected_road",
            )
            self.session.add(segment)
            if first_segment is None:
                first_segment = segment
                await self.session.flush()
        return first_segment

    async def _existing_hashes(self, hashes: list[str]) -> set[str]:
        if not hashes:
            return set()
        prefixed_hashes = [f"etraffic:restriction:{item}" for item in hashes]
        result = await self.session.execute(
            select(RestrictionZone.deduplication_hash).where(RestrictionZone.deduplication_hash.in_(prefixed_hashes))
        )
        return {item.removeprefix("etraffic:restriction:") for item in result.scalars() if item is not None}

    async def _reactivate_existing(self, deduplication_hash: str) -> None:
        hashes = {
            "restriction": f"etraffic:restriction:{deduplication_hash}",
            "incident": f"etraffic:incident:{deduplication_hash}",
        }
        await self.session.execute(update(RestrictionZone).where(RestrictionZone.deduplication_hash == hashes["restriction"]).values(expires_at=None))
        await self.session.execute(update(RoadIncident).where(RoadIncident.deduplication_hash == hashes["incident"]).values(expires_at=None))
        await self.session.execute(
            update(RoadSegment)
            .where(RoadSegment.deduplication_hash.like(f"etraffic:segment:{deduplication_hash}:%"))
            .values(expires_at=None)
        )

    async def _expire_stale_source_records(self, source_id: Any, current_hashes: list[str], expires_at: datetime) -> None:
        current_restriction_hashes = [f"etraffic:restriction:{item}" for item in current_hashes]
        current_incident_hashes = [f"etraffic:incident:{item}" for item in current_hashes]
        await self.session.execute(
            update(RestrictionZone)
            .where(RestrictionZone.source_id == source_id, RestrictionZone.deduplication_hash.not_in(current_restriction_hashes))
            .values(expires_at=expires_at)
        )
        await self.session.execute(
            update(RoadIncident)
            .where(RoadIncident.source_id == source_id, RoadIncident.deduplication_hash.not_in(current_incident_hashes))
            .values(expires_at=expires_at)
        )
        await self.session.execute(
            update(RoadSegment).where(RoadSegment.source_id == source_id).values(expires_at=expires_at)
        )

    async def _expire_fallback_datex(self, expires_at: datetime) -> None:
        result = await self.session.execute(select(DataSource.id).where(DataSource.name == "NAP DATEX traffic restrictions"))
        source_id = result.scalar_one_or_none()
        if source_id is None:
            return
        for model in (RestrictionZone, RoadIncident, RoadSegment):
            await self.session.execute(update(model).where(model.source_id == source_id).values(expires_at=expires_at))

    def _decode_response(self, payload: str) -> str:
        try:
            decoded = bytearray(base64.b64decode(payload))
        except ValueError as exc:
            raise ValidationError("DGT eTraffic response is not base64 encoded") from exc
        for index, value in enumerate(decoded):
            decoded[index] = value ^ ETRAFFIC_DECODER_KEY
        return decoded.decode("utf-8")

    def _geometry(self, value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        if not isinstance(value, str) or not value.strip():
            return None
        try:
            geometry = json.loads(value)
        except json.JSONDecodeError:
            return None
        return geometry if isinstance(geometry, dict) else None

    def _geometry_wkt(self, geometry: dict[str, Any]) -> str | None:
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates")
        if geometry_type == "LineString" and isinstance(coordinates, list):
            return linestring_wkt(coordinates)
        if geometry_type == "MultiLineString" and isinstance(coordinates, list):
            lines = [linestring_wkt(line) for line in coordinates if isinstance(line, list)]
            valid_lines = [line.removeprefix("LINESTRING") for line in lines if line is not None]
            return f"MULTILINESTRING({', '.join(valid_lines)})" if valid_lines else None
        return None

    def _segment_wkts(self, geometry: dict[str, Any]) -> list[str]:
        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates")
        if geometry_type == "LineString" and isinstance(coordinates, list):
            wkt = linestring_wkt(coordinates)
            return [wkt] if wkt is not None else []
        if geometry_type == "MultiLineString" and isinstance(coordinates, list):
            return [wkt for line in coordinates if isinstance(line, list) if (wkt := linestring_wkt(line)) is not None]
        return []

    def _title(self, item: dict[str, Any], kind: str, road_ref: str | None) -> str:
        subtype = self._str(item.get("subtipoVialidad"))
        cause = self._str(item.get("causa"))
        province = self._str(item.get("provinciaIni"))
        parts = [part for part in [kind, subtype, road_ref, province] if part]
        if parts:
            return " - ".join(parts)[:240]
        return (cause or "DGT eTraffic")[:240]

    def _road_incident_kind(self, kind: str) -> RoadIncidentKind:
        lowered = kind.lower()
        if "cortad" in lowered or "restring" in lowered:
            return RoadIncidentKind.OFFICIAL_CLOSURE
        if "lento" in lowered:
            return RoadIncidentKind.REDUCED_VISIBILITY
        return RoadIncidentKind.INSUFFICIENT_DATA

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if value is None:
            return None
        try:
            return datetime.fromisoformat(value).replace(tzinfo=UTC)
        except ValueError:
            return None

    def _str(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _hash(self, external_id: str, payload: dict[str, Any]) -> str:
        stable = f"{external_id}|{json.dumps(payload, sort_keys=True, default=str)}"
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()
