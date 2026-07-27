import asyncio
import hashlib
import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.enums import IngestionRunStatus, ProvenanceType, VerificationStatus
from app.domain.models import DataIngestionRun, DataSource, RestrictionZone, RoadSegment
from app.infrastructure.object_storage import put_text_object
from app.ingestion.base import BaseConnector, ConnectorMetrics, ConnectorRunResult, ValidationError
from app.ingestion.config import IgnConnectorConfig
from app.ingestion.spatial import geojson_geometry_to_linestring_wkt, geometry_hash_payload


@dataclass(frozen=True)
class IgnRoadRecord:
    external_id: str
    geometry_wkt: str
    original_metadata: dict[str, Any]
    deduplication_hash: str


class IgnTransportConnector(BaseConnector[str, IgnRoadRecord]):
    name = "ign_transport_features"

    def __init__(
        self,
        session: AsyncSession,
        config: IgnConnectorConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.session = session
        self.config = config or IgnConnectorConfig.from_settings(get_settings())
        self.http_client = http_client

    async def fetch(self) -> str:
        url = f"{self.config.wfs_base_url.rstrip('/')}/collections/{self.config.transport_typename}/items"
        features: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        target_bboxes = await self._target_bboxes()
        for bbox in target_bboxes:
            offset = 0
            pages = 0
            while len(features) < self.config.max_features and pages < self.config.max_pages_per_tile:
                params = {
                    "f": "json",
                    "bbox": bbox,
                    "limit": str(self.config.feature_limit),
                    "offset": str(offset),
                }
                response = await self._request(url, params)
                response.raise_for_status()
                payload = response.json()
                page_features = payload.get("features") if isinstance(payload, dict) else None
                if not isinstance(page_features, list) or not page_features:
                    break
                for feature in page_features:
                    if not isinstance(feature, dict):
                        continue
                    feature_id = str(feature.get("id") or self._hash(json.dumps(feature, sort_keys=True), {}))
                    if feature_id in seen_ids:
                        continue
                    seen_ids.add(feature_id)
                    features.append(feature)
                    if len(features) >= self.config.max_features:
                        break
                if len(page_features) < self.config.feature_limit:
                    break
                offset += self.config.feature_limit
                pages += 1
        return json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False)

    def validate(self, raw: str) -> None:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
            raise ValidationError("IGN OGC API response must be a GeoJSON FeatureCollection")
        if not isinstance(payload.get("features"), list):
            raise ValidationError("IGN OGC API response missing features array")

    def normalize(self, raw: str) -> list[IgnRoadRecord]:
        payload = json.loads(raw)
        records: list[IgnRoadRecord] = []
        for feature in payload.get("features", []):
            if not isinstance(feature, dict):
                continue
            geometry = feature.get("geometry")
            properties = feature.get("properties", {})
            if not isinstance(geometry, dict) or not isinstance(properties, dict):
                continue
            geometry_wkt = geojson_geometry_to_linestring_wkt(geometry)
            if geometry_wkt is None:
                continue
            external_id = str(feature.get("id") or properties.get("localId") or self._hash(geometry_hash_payload(geometry), properties))
            records.append(
                IgnRoadRecord(
                    external_id=external_id,
                    geometry_wkt=geometry_wkt,
                    original_metadata={"properties": properties, "geometry": geometry, "crs": "EPSG:4326"},
                    deduplication_hash=self._hash(external_id, properties),
                )
            )
        return records

    def deduplicate(self, records: list[IgnRoadRecord]) -> tuple[list[IgnRoadRecord], int]:
        seen: set[str] = set()
        unique: list[IgnRoadRecord] = []
        duplicates = 0
        for record in records:
            if record.deduplication_hash in seen:
                duplicates += 1
                continue
            seen.add(record.deduplication_hash)
            unique.append(record)
        return unique, duplicates

    async def persist(self, records: list[IgnRoadRecord], raw: str) -> ConnectorMetrics:
        started_at = datetime.now(UTC)
        source = await self._get_or_create_source()
        raw_uri = await asyncio.to_thread(
            put_text_object,
            f"ign/transport/{started_at:%Y/%m/%d/%H%M%S}.geojson",
            raw,
            "application/geo+json",
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
            props = record.original_metadata.get("properties", {})
            props_dict = props if isinstance(props, dict) else {}
            self.session.add(
                RoadSegment(
                    source_id=source.id,
                    external_id=record.external_id,
                    provenance=ProvenanceType.OFFICIAL,
                    received_at=started_at,
                    verification_status=VerificationStatus.PENDING,
                    original_metadata=record.original_metadata,
                    deduplication_hash=record.deduplication_hash,
                    geometry=WKTElement(record.geometry_wkt, srid=4326),
                    original_crs="EPSG:4326",
                    name=self._str(props_dict.get("name") or props_dict.get("nombre")),
                    road_ref=self._str(props_dict.get("nationalRoadCode") or props_dict.get("localId")),
                    road_class=self._str(props_dict.get("formOfWay") or props_dict.get("roadClass")),
                )
            )
            persisted += 1
        run.status = IngestionRunStatus.COMPLETED
        run.finished_at = datetime.now(UTC)
        run.received_count = len(records)
        run.duplicate_count = duplicates
        run.persisted_count = persisted
        run.metrics = {"typename": self.config.transport_typename, "bbox": self.config.area_bbox}
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
                f"ign/dead-letter/{started_at:%Y/%m/%d/%H%M%S}.json",
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

    async def _request(self, url: str, params: dict[str, str]) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                if self.http_client is not None:
                    return await self.http_client.get(url, params=params, timeout=self.config.timeout_seconds)
                async with httpx.AsyncClient() as client:
                    return await client.get(url, params=params, timeout=self.config.timeout_seconds)
            except (httpx.TimeoutException, httpx.HTTPError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
        raise ValidationError(f"IGN OGC API fetch failed: {last_error}")

    async def _get_or_create_source(self) -> DataSource:
        result = await self.session.execute(select(DataSource).where(DataSource.name == "IGN/CNIG Transport OGC API"))
        source = result.scalar_one_or_none()
        if source is not None:
            return source
        source = DataSource(
            name="IGN/CNIG Transport OGC API",
            source_type=ProvenanceType.OFFICIAL,
            authority="Instituto Geografico Nacional / CNIG",
            base_url=self.config.wfs_base_url,
            license_name="CNIG politica de datos",
            attribution="IGN/CNIG",
            update_frequency="as published by CNIG WFS",
            reliability_score=0.9,
            source_metadata={"collection": self.config.transport_typename},
        )
        self.session.add(source)
        await self.session.flush()
        return source

    async def _target_bboxes(self) -> list[str]:
        if not self.config.target_datex_restrictions or not hasattr(self.session, "execute"):
            return _bbox_tiles(self.config.area_bbox, self.config.tile_size_degrees)
        result = await self.session.execute(
            select(RestrictionZone.original_metadata)
            .join(DataSource, DataSource.id == RestrictionZone.source_id)
            .where(DataSource.name == "NAP DATEX traffic restrictions", RestrictionZone.expires_at.is_(None))
            .limit(2000)
        )
        cells: set[tuple[int, int]] = set()
        cell_size = 0.25
        for metadata in result.scalars():
            if not isinstance(metadata, dict):
                continue
            coordinates = metadata.get("nap_coordinates")
            if not isinstance(coordinates, list):
                continue
            for coord in coordinates:
                pair = _coord_pair(coord)
                if pair is None:
                    continue
                cells.add((math.floor(pair[0] / cell_size), math.floor(pair[1] / cell_size)))
        if not cells:
            return _bbox_tiles(self.config.area_bbox, self.config.tile_size_degrees)
        return [
            f"{west},{south},{west + cell_size},{south + cell_size}"
            for west_index, south_index in sorted(cells)
            for west, south in [(west_index * cell_size, south_index * cell_size)]
        ]

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


def _bbox_tiles(area_bbox: str, tile_size: float) -> list[str]:
    west, south, east, north = (float(part.strip()) for part in area_bbox.split(","))
    size = max(tile_size, 0.1)
    tiles: list[str] = []
    tile_west = west
    while tile_west < east:
        tile_east = min(tile_west + size, east)
        tile_south = south
        while tile_south < north:
            tile_north = min(tile_south + size, north)
            tiles.append(f"{tile_west},{tile_south},{tile_east},{tile_north}")
            tile_south = tile_north
        tile_west = tile_east
    return tiles


def _coord_pair(value: Any) -> list[float] | None:
    if not isinstance(value, list | tuple) or len(value) < 2:
        return None
    try:
        longitude = float(value[0])
        latitude = float(value[1])
    except (TypeError, ValueError):
        return None
    if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
        return None
    return [longitude, latitude]
