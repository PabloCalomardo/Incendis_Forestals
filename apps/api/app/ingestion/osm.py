import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.enums import IngestionRunStatus, ProvenanceType, VerificationStatus
from app.domain.models import DataIngestionRun, DataSource, RoadSegment
from app.infrastructure.object_storage import put_text_object
from app.ingestion.base import BaseConnector, ConnectorMetrics, ConnectorRunResult, ValidationError
from app.ingestion.config import OsmConnectorConfig
from app.ingestion.spatial import bbox_to_overpass_tuple, linestring_wkt

OSM_ROAD_TAGS = {"highway", "surface", "width", "access", "maxweight", "incline", "tracktype", "smoothness"}


@dataclass(frozen=True)
class OsmRoadRecord:
    external_id: str
    geometry_wkt: str
    tags: dict[str, Any]
    deduplication_hash: str


class OsmRoadConnector(BaseConnector[str, OsmRoadRecord]):
    name = "osm_overpass_roads"

    def __init__(
        self,
        session: AsyncSession,
        config: OsmConnectorConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.session = session
        self.config = config or OsmConnectorConfig.from_settings(get_settings())
        self.http_client = http_client

    async def fetch(self) -> str:
        query = self._query()
        response = await self._request(query)
        response.raise_for_status()
        return response.text

    def validate(self, raw: str) -> None:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("elements"), list):
            raise ValidationError("OSM Overpass response must include elements array")

    def normalize(self, raw: str) -> list[OsmRoadRecord]:
        payload = json.loads(raw)
        records: list[OsmRoadRecord] = []
        for element in payload.get("elements", []):
            if not isinstance(element, dict) or element.get("type") != "way":
                continue
            geometry = element.get("geometry")
            tags = element.get("tags", {})
            if not isinstance(geometry, list) or not isinstance(tags, dict):
                continue
            coords = [[point.get("lon"), point.get("lat")] for point in geometry if isinstance(point, dict)]
            numeric_coords = [[float(lon), float(lat)] for lon, lat in coords if lon is not None and lat is not None]
            geometry_wkt = linestring_wkt(numeric_coords)
            if geometry_wkt is None:
                continue
            external_id = f"osm-way:{element.get('id')}"
            retained_tags = {key: tags.get(key) for key in OSM_ROAD_TAGS if key in tags}
            records.append(
                OsmRoadRecord(
                    external_id=external_id,
                    geometry_wkt=geometry_wkt,
                    tags={**retained_tags, "all_tags": tags},
                    deduplication_hash=self._hash(external_id, retained_tags),
                )
            )
        return records

    def deduplicate(self, records: list[OsmRoadRecord]) -> tuple[list[OsmRoadRecord], int]:
        seen: set[str] = set()
        unique: list[OsmRoadRecord] = []
        duplicates = 0
        for record in records:
            if record.deduplication_hash in seen:
                duplicates += 1
                continue
            seen.add(record.deduplication_hash)
            unique.append(record)
        return unique, duplicates

    async def persist(self, records: list[OsmRoadRecord], raw: str) -> ConnectorMetrics:
        started_at = datetime.now(UTC)
        source = await self._get_or_create_source()
        raw_uri = await asyncio.to_thread(
            put_text_object,
            f"osm/roads/{started_at:%Y/%m/%d/%H%M%S}.json",
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
            tags = record.tags
            self.session.add(
                RoadSegment(
                    source_id=source.id,
                    external_id=record.external_id,
                    provenance=ProvenanceType.OBSERVED,
                    received_at=started_at,
                    verification_status=VerificationStatus.PENDING,
                    original_metadata=tags,
                    deduplication_hash=record.deduplication_hash,
                    geometry=WKTElement(record.geometry_wkt, srid=4326),
                    original_crs="EPSG:4326",
                    name=self._str(tags.get("name")),
                    road_ref=self._str(tags.get("ref")),
                    road_class=self._str(tags.get("highway")),
                    surface=self._str(tags.get("surface")),
                    width_meters=self._float(tags.get("width")),
                    access=self._str(tags.get("access")),
                    max_weight_tons=self._float(tags.get("maxweight")),
                    incline=self._str(tags.get("incline")),
                )
            )
            persisted += 1
        run.status = IngestionRunStatus.COMPLETED
        run.finished_at = datetime.now(UTC)
        run.received_count = len(records)
        run.duplicate_count = duplicates
        run.persisted_count = persisted
        run.metrics = {"bbox": self.config.area_bbox, "feature_limit": self.config.feature_limit}
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
            metrics = await self.record_failure(started_at, exc, raw)
            return ConnectorRunResult(self.name, "failed", started_at, datetime.now(UTC), metrics)

    async def record_failure(self, started_at: datetime, error: Exception, raw: str | None = None) -> ConnectorMetrics:
        raw_uri = None
        if raw:
            raw_uri = await asyncio.to_thread(
                put_text_object,
                f"osm/dead-letter/{started_at:%Y/%m/%d/%H%M%S}.json",
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

    def _query(self) -> str:
        bbox = bbox_to_overpass_tuple(self.config.area_bbox)
        return f"""
[out:json][timeout:{self.config.timeout_seconds}];
(
  way["highway"]({bbox});
);
out tags geom {self.config.feature_limit};
"""

    async def _request(self, query: str) -> httpx.Response:
        headers = {"User-Agent": "wildfire-intelligence-platform/0.1"}
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                if self.http_client is not None:
                    return await self.http_client.post(
                        self.config.overpass_url,
                        data={"data": query},
                        headers=headers,
                        timeout=self.config.timeout_seconds,
                    )
                async with httpx.AsyncClient() as client:
                    return await client.post(
                        self.config.overpass_url,
                        data={"data": query},
                        headers=headers,
                        timeout=self.config.timeout_seconds,
                    )
            except (httpx.TimeoutException, httpx.HTTPError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
        raise ValidationError(f"OSM Overpass fetch failed: {last_error}")

    async def _get_or_create_source(self) -> DataSource:
        result = await self.session.execute(select(DataSource).where(DataSource.name == "OpenStreetMap Overpass"))
        source = result.scalar_one_or_none()
        if source is not None:
            return source
        source = DataSource(
            name="OpenStreetMap Overpass",
            source_type=ProvenanceType.OBSERVED,
            authority="OpenStreetMap contributors",
            base_url=self.config.overpass_url,
            license_name="ODbL 1.0",
            attribution="OpenStreetMap contributors",
            update_frequency="near-real-time Overpass replication",
            reliability_score=0.7,
            source_metadata={"strategy": "bounded Overpass query; bulk imports must use extracts"},
        )
        self.session.add(source)
        await self.session.flush()
        return source

    async def _existing_hashes(self, hashes: list[str]) -> set[str]:
        if not hashes:
            return set()
        result = await self.session.execute(select(RoadSegment.deduplication_hash).where(RoadSegment.deduplication_hash.in_(hashes)))
        return {item for item in result.scalars() if item is not None}

    def _hash(self, external_id: str, payload: dict[str, Any]) -> str:
        stable = f"{external_id}|{json.dumps(payload, sort_keys=True, default=str)}"
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()

    def _str(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _float(self, value: Any) -> float | None:
        text = self._str(value)
        if text is None:
            return None
        cleaned = text.replace("t", "").replace(",", ".").strip()
        try:
            return float(cleaned)
        except ValueError:
            return None
