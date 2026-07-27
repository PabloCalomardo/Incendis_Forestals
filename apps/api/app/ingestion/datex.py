import asyncio
import hashlib
import heapq
import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from geoalchemy2.elements import WKTElement
from sqlalchemy import Integer, and_, func, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.enums import IngestionRunStatus, ProvenanceType, RoadIncidentKind, VerificationStatus, ZoneKind
from app.domain.models import DataIngestionRun, DataSource, RestrictionZone, RoadIncident, RoadSegment
from app.infrastructure.object_storage import put_text_object
from app.ingestion.base import BaseConnector, ConnectorMetrics, ConnectorRunResult, ValidationError
from app.ingestion.config import DatexConnectorConfig
from app.ingestion.spatial import linestring_wkt

CAUSE_LABELS = {
    "abnormalTraffic": "Transit anormal",
    "accident": "Accident",
    "environmentalObstruction": "Obstacle ambiental",
    "infrastructureDamage": "Dany a la infraestructura",
    "obstruction": "Obstacle",
    "poorEnvironmentConditions": "Condicions ambientals adverses",
    "roadMaintenance": "Obres o manteniment",
}
DETAIL_LABELS = {
    "fire": "Incendi",
    "roadworks": "Obres",
    "vehicleOnFire": "Vehicle incendiat",
}
LANE_LABELS = {
    "allLanesCompleteCarriageway": "Tots els carrils",
    "leftLane": "Carril esquerre",
    "rightLane": "Carril dret",
    "middleLane": "Carril central",
    "hardShoulder": "Vorera",
}
DIRECTION_LABELS = {
    "both": "Ambdós sentits",
    "positive": "Sentit creixent",
    "negative": "Sentit decreixent",
    "unknown": "Desconegut",
}
SERVICE_LEVEL_LABELS = {
    "low": "Verd",
    "medium": "Groc",
    "high": "Vermell",
    "highest": "Negre",
}


@dataclass(frozen=True)
class DatexRawPayload:
    feeds: dict[str, str]


@dataclass(frozen=True)
class DatexRestrictionRecord:
    external_id: str
    feed_url: str
    kind: str
    title: str
    road_ref: str | None
    geometry_wkt: str
    segment_wkts: list[str]
    observed_at: datetime | None
    expires_at: datetime | None
    original_metadata: dict[str, Any]
    deduplication_hash: str


@dataclass(frozen=True)
class MatchedRoadGeometry:
    geometry_wkt: str
    segment_wkts: list[str]
    strategy: str


class DatexTrafficConnector(BaseConnector[DatexRawPayload, DatexRestrictionRecord]):
    name = "nap_datex_traffic_restrictions"

    def __init__(
        self,
        session: AsyncSession,
        config: DatexConnectorConfig | None = None,
        http_client: httpx.AsyncClient | None = None,
        unlimited_road_enrichment: bool = False,
    ) -> None:
        self.session = session
        self.config = config or DatexConnectorConfig.from_settings(get_settings())
        self.http_client = http_client
        self._road_geometry_cache: dict[str, MatchedRoadGeometry | None] = {}
        self._cnig_lines_cache: dict[str, list[list[list[float]]]] = {}
        self._pk_point_cache: dict[str, list[list[float]]] = {}
        self._pk_sample_budget: int | None = None if unlimited_road_enrichment else self.config.pk_sample_budget
        self._osrm_budget: int | None = None if unlimited_road_enrichment else 350
        self._overpass_budget = 20

    async def fetch(self) -> DatexRawPayload:
        if not self.config.feed_urls:
            raise ValidationError("DATEX feed URLs are empty")
        feeds: dict[str, str] = {}
        for url in self.config.feed_urls:
            response = await self._request(url)
            response.raise_for_status()
            feeds[url] = response.text
        return DatexRawPayload(feeds=feeds)

    def validate(self, raw: DatexRawPayload) -> None:
        if not raw.feeds:
            raise ValidationError("DATEX payload has no feeds")
        for content in raw.feeds.values():
            root = ET.fromstring(content)
            if _local_name(root.tag) not in {"d2LogicalModel", "payload"}:
                raise ValidationError("DATEX response must be a d2LogicalModel or payload document")

    def normalize(self, raw: DatexRawPayload) -> list[DatexRestrictionRecord]:
        records: list[DatexRestrictionRecord] = []
        for feed_url, content in raw.feeds.items():
            root = ET.fromstring(content)
            for situation in _children(root, "situation"):
                situation_id = situation.attrib.get("id") or self._hash(feed_url, {"xml": ET.tostring(situation, encoding="unicode")})[:16]
                for record in _children(situation, "situationRecord"):
                    normalized = self._normalize_record(feed_url, situation_id, record, root)
                    if normalized is not None:
                        records.append(normalized)
        return records

    def deduplicate(self, records: list[DatexRestrictionRecord]) -> tuple[list[DatexRestrictionRecord], int]:
        seen: set[str] = set()
        unique: list[DatexRestrictionRecord] = []
        duplicates = 0
        for record in records:
            if record.deduplication_hash in seen:
                duplicates += 1
                continue
            seen.add(record.deduplication_hash)
            unique.append(record)
        return unique, duplicates

    async def persist(self, records: list[DatexRestrictionRecord], raw: DatexRawPayload) -> ConnectorMetrics:
        started_at = datetime.now(UTC)
        source = await self._get_or_create_source()
        raw_text = json.dumps(raw.feeds, ensure_ascii=False)
        raw_uri = await asyncio.to_thread(
            put_text_object,
            f"datex/traffic/{started_at:%Y/%m/%d/%H%M%S}.json",
            raw_text,
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
        current_hashes = [record.deduplication_hash for record in records]
        await self._expire_stale_records(source.id, current_hashes, started_at)
        existing = await self._existing_hashes([record.deduplication_hash for record in records])
        persisted = 0
        duplicates = 0
        for record in records:
            record = await self._with_road_following_geometry(record, source.id)
            if record.deduplication_hash in existing:
                duplicates += 1
                await self._reactivate_existing(record, source.id, started_at)
                continue
            first_segment: RoadSegment | None = None
            for index, segment_wkt in enumerate(record.segment_wkts):
                segment = RoadSegment(
                    source_id=source.id,
                    external_id=f"{record.external_id}:segment:{index}",
                    provenance=ProvenanceType.OFFICIAL,
                    observed_at=record.observed_at,
                    received_at=started_at,
                    expires_at=record.expires_at,
                    verification_status=VerificationStatus.PENDING,
                    confidence=0.93,
                    original_metadata={**record.original_metadata, "segment_index": index},
                    deduplication_hash=f"segment:{record.deduplication_hash}:{index}",
                    geometry=WKTElement(segment_wkt, srid=4326),
                    original_crs="EPSG:4326",
                    name=record.title[:160],
                    road_ref=record.road_ref,
                    road_class="nap_datex_affected_road",
                )
                self.session.add(segment)
                if first_segment is None:
                    first_segment = segment
                    await self.session.flush()
            if first_segment is None:
                continue
            self.session.add(
                RoadIncident(
                    source_id=source.id,
                    external_id=f"{record.external_id}:incident",
                    provenance=ProvenanceType.OFFICIAL,
                    observed_at=record.observed_at,
                    received_at=started_at,
                    expires_at=record.expires_at,
                    verification_status=VerificationStatus.PENDING,
                    confidence=0.93,
                    original_metadata=record.original_metadata,
                    deduplication_hash=f"incident:{record.deduplication_hash}",
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
                expires_at=record.expires_at,
                verification_status=VerificationStatus.PENDING,
                confidence=0.93,
                original_metadata=record.original_metadata,
                deduplication_hash=f"restriction:{record.deduplication_hash}",
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
        run.metrics = {"feeds": list(raw.feeds.keys())}
        await self.session.commit()
        return ConnectorMetrics(received=len(records), duplicated=duplicates, persisted=persisted, raw_object_uri=raw_uri)

    async def report_metrics(self, metrics: ConnectorMetrics) -> None:
        return None

    async def enrich_pending_routes(self, limit: int = 10, road_ref: str | None = None) -> dict[str, int]:
        metadata = RestrictionZone.original_metadata
        attempts = func.coalesce(metadata["road_enrichment_attempts"].astext.cast(Integer), 0)
        conditions = [
            RestrictionZone.expires_at.is_(None),
            metadata["geometry_strategy"].astext == "nap_datex_coordinates",
            metadata["road_ref"].astext.is_not(None),
            metadata["kilometer_range"].astext.is_not(None),
            func.ST_NPoints(RestrictionZone.geometry) <= 2,
        ]
        if road_ref:
            conditions.append(func.upper(metadata["road_ref"].astext) == road_ref.strip().upper())
        result = await self.session.execute(
            select(RestrictionZone, func.ST_AsGeoJSON(RestrictionZone.geometry))
            .where(*conditions)
            .order_by(attempts.asc(), RestrictionZone.updated_at.asc())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        rows = result.all()
        enriched = 0
        failed = 0
        for zone, geometry_json in rows:
            original_metadata = dict(zone.original_metadata)
            geometry = json.loads(geometry_json)
            coordinates = geometry.get("coordinates")
            if geometry.get("type") != "LineString" or not isinstance(coordinates, list):
                failed += 1
                continue
            geometry_wkt = linestring_wkt(coordinates)
            if geometry_wkt is None:
                failed += 1
                continue
            record = DatexRestrictionRecord(
                external_id=zone.external_id or str(zone.id),
                feed_url=str(original_metadata.get("feed_url") or ""),
                kind=zone.restriction_type,
                title=zone.name,
                road_ref=str(original_metadata.get("road_ref")),
                geometry_wkt=geometry_wkt,
                segment_wkts=[geometry_wkt],
                observed_at=zone.observed_at,
                expires_at=zone.expires_at,
                original_metadata=original_metadata,
                deduplication_hash=zone.deduplication_hash or str(zone.id),
            )
            matched = await self._with_road_following_geometry(record, zone.source_id)
            next_metadata = {
                **original_metadata,
                "road_enrichment_attempts": int(original_metadata.get("road_enrichment_attempts") or 0) + 1,
                "road_enrichment_last_attempt_at": datetime.now(UTC).isoformat(),
            }
            if matched.original_metadata.get("geometry_strategy") == "nap_datex_coordinates":
                next_metadata["road_enrichment_status"] = "pending"
                failed += 1
            else:
                next_metadata.update(matched.original_metadata)
                next_metadata["road_enrichment_status"] = "completed"
                enriched += 1
            await self.session.execute(
                update(RestrictionZone)
                .where(RestrictionZone.id == zone.id)
                .values(
                    geometry=WKTElement(matched.geometry_wkt, srid=4326),
                    original_metadata=next_metadata,
                )
            )
        await self.session.commit()
        return {"selected": len(rows), "enriched": enriched, "pending": failed}

    async def execute(self) -> ConnectorRunResult:
        started_at = datetime.now(UTC)
        raw: DatexRawPayload | None = None
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

    async def record_failure(self, started_at: datetime, error: Exception, raw: DatexRawPayload | None = None) -> ConnectorMetrics:
        raw_uri = None
        if raw:
            raw_uri = await asyncio.to_thread(
                put_text_object,
                f"datex/dead-letter/{started_at:%Y/%m/%d/%H%M%S}.json",
                json.dumps(raw.feeds, ensure_ascii=False),
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

    def _normalize_record(
        self,
        feed_url: str,
        situation_id: str,
        record: ET.Element,
        root: ET.Element,
    ) -> DatexRestrictionRecord | None:
        coordinates = _coordinates(record)
        geometry_wkt = linestring_wkt(coordinates)
        if geometry_wkt is None and len(coordinates) == 1:
            lon, lat = coordinates[0]
            geometry_wkt = linestring_wkt([[lon - 0.0002, lat - 0.0002], [lon + 0.0002, lat + 0.0002]])
        if geometry_wkt is None:
            return None
        segment_wkts = [geometry_wkt] if geometry_wkt.startswith("LINESTRING") else []
        record_id = record.attrib.get("id") or _text(record, "situationRecordCreationReference") or situation_id
        external_id = f"{feed_url}#{record_id}"
        road_ref = _first_text(record, ["roadNumber", "roadName"])
        record_type = _record_type(record)
        category = _functional_category(record)
        details = _datex_details(record)
        title = _title(record, record_type, road_ref, details)
        metadata = {
            "feed_url": feed_url,
            "situation_id": situation_id,
            "record_id": record_id,
            "record_type": record_type,
            "functional_category": category,
            "road_ref": road_ref,
            **details,
            "comments": _texts(record, "value"),
            "validity_status": _text(record, "validityStatus"),
            "datex_root": _local_name(root.tag),
            "geometry_strategy": "nap_datex_coordinates",
            "nap_coordinates": coordinates,
        }
        return DatexRestrictionRecord(
            external_id=external_id,
            feed_url=feed_url,
            kind=category,
            title=title,
            road_ref=road_ref,
            geometry_wkt=geometry_wkt,
            segment_wkts=segment_wkts,
            observed_at=_parse_datetime(_first_text(record, ["overallStartTime", "situationRecordCreationTime"])),
            expires_at=_parse_datetime(_text(record, "overallEndTime")),
            original_metadata=metadata,
            deduplication_hash=self._hash(external_id, metadata),
        )

    async def _with_road_following_geometry(self, record: DatexRestrictionRecord, source_id: Any) -> DatexRestrictionRecord:
        if not record.road_ref or len(record.segment_wkts) != 1:
            return record
        coordinates = record.original_metadata.get("nap_coordinates")
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            return record
        start = _coord_pair(coordinates[0])
        end = _coord_pair(coordinates[-1])
        if start is None or end is None:
            return record
        matched = await self._matched_road_geometry(
            record,
            record.road_ref,
            start,
            end,
            source_id,
            kilometer_bounds=_kilometer_bounds(record),
            allow_osrm=_should_try_osrm(start, end),
            allow_overpass=_should_try_overpass(record, start, end),
        )
        if matched is None:
            return record
        metadata = {**record.original_metadata, "geometry_strategy": matched.strategy}
        return DatexRestrictionRecord(
            external_id=record.external_id,
            feed_url=record.feed_url,
            kind=record.kind,
            title=record.title,
            road_ref=record.road_ref,
            geometry_wkt=matched.geometry_wkt,
            segment_wkts=matched.segment_wkts,
            observed_at=record.observed_at,
            expires_at=record.expires_at,
            original_metadata=metadata,
            deduplication_hash=record.deduplication_hash,
        )

    async def _matched_road_geometry(
        self,
        record: DatexRestrictionRecord,
        road_ref: str,
        start: list[float],
        end: list[float],
        source_id: Any,
        kilometer_bounds: tuple[float, float] | None,
        allow_osrm: bool,
        allow_overpass: bool,
    ) -> MatchedRoadGeometry | None:
        cache_key = _road_cache_key(road_ref, start, end)
        if cache_key in self._road_geometry_cache:
            return self._road_geometry_cache[cache_key]
        matched = await self._cnig_road_geometry(road_ref, start, end, kilometer_bounds)
        if matched is None:
            matched = await self._previous_road_geometry(record, road_ref, start, end, source_id)
        if matched is None:
            matched = await self._pk_sampled_road_geometry(record, road_ref, start, end, kilometer_bounds)
        if matched is None:
            matched = await self._local_road_geometry(road_ref, start, end, source_id)
        if matched is None and allow_overpass:
            matched = await self._overpass_road_geometry(road_ref, start, end)
        if matched is None and allow_osrm:
            matched = await self._osrm_road_geometry(road_ref, start, end)
        self._road_geometry_cache[cache_key] = matched
        return matched

    async def _cnig_road_geometry(
        self,
        road_ref: str,
        start: list[float],
        end: list[float],
        kilometer_bounds: tuple[float, float] | None = None,
    ) -> MatchedRoadGeometry | None:
        available = await self.session.execute(select(func.to_regclass("public.cnig_road_segments")))
        if available.scalar_one_or_none() is None:
            return None
        normalized_ref = road_ref.strip().upper()
        anchors = (start, end)
        if kilometer_bounds is not None:
            kilometer_anchors: list[list[float]] = []
            for kilometer in kilometer_bounds:
                result = await self.session.execute(
                    text(
                        """
                        SELECT ST_X(geometry), ST_Y(geometry)
                        FROM cnig_road_kilometers
                        WHERE upper(nombre) = :road_ref
                          AND numero ~ '^[0-9]+([.,][0-9]+)?$'
                        ORDER BY abs(replace(numero, ',', '.')::double precision - :kilometer),
                                 ST_Distance(geometry, ST_SetSRID(ST_Point(:lon, :lat), 4326))
                        LIMIT 1
                        """
                    ),
                    {"road_ref": normalized_ref, "kilometer": kilometer, "lon": start[0], "lat": start[1]},
                )
                point = result.first()
                if point is not None:
                    kilometer_anchors.append([float(point[0]), float(point[1])])
            if len(kilometer_anchors) == 2:
                anchors = (kilometer_anchors[0], kilometer_anchors[1])

        lines = self._cnig_lines_cache.get(normalized_ref)
        if lines is None:
            result = await self.session.execute(
                text(
                    """
                    SELECT ST_AsGeoJSON(geometry)
                    FROM cnig_road_segments
                    WHERE upper(coalesce(nombre, '')) = :road_ref
                       OR upper(coalesce(codigo, '')) = :road_ref
                    """
                ),
                {"road_ref": normalized_ref},
            )
            lines = []
            for geometry_json in result.scalars():
                geometry = json.loads(geometry_json)
                coordinates = geometry.get("coordinates")
                if geometry.get("type") == "LineString" and isinstance(coordinates, list):
                    line = [_coord_pair(coordinate) for coordinate in coordinates]
                    valid_line = [coordinate for coordinate in line if coordinate is not None]
                    if len(valid_line) >= 2:
                        lines.append(valid_line)
            self._cnig_lines_cache[normalized_ref] = lines
        route = _road_graph_route(lines, anchors[0], anchors[1])
        if route is None or not _route_is_reasonable(route, anchors[0], anchors[1]):
            return None
        return _matched_geometry([route], "cnig_local_road_network")

    async def _previous_road_geometry(
        self,
        record: DatexRestrictionRecord,
        road_ref: str,
        start: list[float],
        end: list[float],
        source_id: Any,
    ) -> MatchedRoadGeometry | None:
        kilometer_range = record.original_metadata.get("kilometer_range")
        if not kilometer_range:
            return None
        metadata = RestrictionZone.original_metadata
        start_point = func.ST_SetSRID(func.ST_Point(start[0], start[1]), 4326)
        end_point = func.ST_SetSRID(func.ST_Point(end[0], end[1]), 4326)
        same_section = and_(
            func.ST_DWithin(RestrictionZone.geometry, start_point, 0.03),
            func.ST_DWithin(RestrictionZone.geometry, end_point, 0.03),
        )
        exact_kilometer_range = metadata["kilometer_range"].astext == str(kilometer_range)
        result = await self.session.execute(
            select(func.ST_AsGeoJSON(RestrictionZone.geometry))
            .where(
                RestrictionZone.source_id == source_id,
                metadata["road_ref"].astext == road_ref,
                or_(exact_kilometer_range, same_section),
                func.ST_NPoints(RestrictionZone.geometry) > 2,
            )
            .order_by(RestrictionZone.updated_at.desc())
            .limit(1)
        )
        geometry_json = result.scalar_one_or_none()
        if not geometry_json:
            return None
        geometry = json.loads(geometry_json)
        raw_lines = geometry.get("coordinates")
        if geometry.get("type") == "LineString":
            raw_lines = [raw_lines]
        if not isinstance(raw_lines, list):
            return None
        lines: list[list[list[float]]] = []
        for raw_line in raw_lines:
            if not isinstance(raw_line, list):
                continue
            line = [_coord_pair(coordinate) for coordinate in raw_line]
            valid_line = [coordinate for coordinate in line if coordinate is not None]
            if len(valid_line) > 2:
                lines.append(valid_line)
        return _matched_geometry(lines, "previous_road_geometry_reuse")

    async def _pk_sampled_road_geometry(
        self,
        record: DatexRestrictionRecord,
        road_ref: str,
        start: list[float],
        end: list[float],
        kilometer_bounds: tuple[float, float] | None,
    ) -> MatchedRoadGeometry | None:
        if kilometer_bounds is None:
            return None
        first_km, last_km = kilometer_bounds
        distance_km = abs(last_km - first_km)
        if not _should_try_pk_sampling(record, distance_km):
            return None
        sample_values = _pk_sample_values(first_km, last_km, self.config.pk_sample_step_km)
        record.original_metadata["road_enrichment_pk_samples_requested"] = len(sample_values)
        if self._pk_sample_budget is not None and len(sample_values) > self._pk_sample_budget:
            return None
        points: list[list[float]] = []
        previous: list[float] | None = None
        anchor_first = start if _distance_degrees(start, end) < 1.2 else None
        anchor_last = end if _distance_degrees(start, end) < 1.2 else None
        for index, km in enumerate(sample_values):
            candidates = await self._pk_to_lonlat_candidates(road_ref, km)
            if not candidates:
                continue
            if index == 0 and anchor_first is not None:
                point = min(candidates, key=lambda candidate: _distance_degrees(candidate, anchor_first))
            elif index == len(sample_values) - 1 and anchor_last is not None:
                point = min(candidates, key=lambda candidate: _distance_degrees(candidate, anchor_last))
            elif previous is not None:
                previous_point = previous
                point = min(candidates, key=lambda candidate: _distance_degrees(candidate, previous_point))
            else:
                point = candidates[0]
            if previous is None or _distance_degrees(point, previous) > 0.00001:
                points.append(point)
                previous = point
        record.original_metadata["road_enrichment_pk_samples_resolved"] = len(points)
        if len(points) < 2:
            return None
        routed_points = await self._route_pk_waypoints(points)
        return _matched_geometry([routed_points], "dgt_pk_waypoint_routing")

    async def _route_pk_waypoints(self, points: list[list[float]]) -> list[list[float]]:
        routed: list[list[float]] = []
        for index in range(1, len(points)):
            start = points[index - 1]
            end = points[index]
            segment = await self._osrm_segment_geometry(start, end)
            if segment is None:
                segment = [start, end]
            if not routed:
                routed.extend(segment)
            else:
                routed.extend(segment[1:])
        return routed

    async def _osrm_segment_geometry(self, start: list[float], end: list[float]) -> list[list[float]] | None:
        if self._osrm_budget is not None and self._osrm_budget <= 0:
            return None
        if self._osrm_budget is not None:
            self._osrm_budget -= 1
        url = f"{self.config.osrm_route_url.rstrip('/')}/{start[0]},{start[1]};{end[0]},{end[1]}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    params={"overview": "full", "geometries": "geojson", "steps": "false", "alternatives": "false"},
                    headers={"User-Agent": "wildfire-intelligence-platform/0.1"},
                    timeout=self.config.osrm_timeout_seconds,
                )
            if response.status_code in {429, 500, 502, 503, 504}:
                if self._osrm_budget is not None:
                    self._osrm_budget = 0
                return None
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        if payload.get("code") != "Ok":
            return None
        routes = payload.get("routes")
        if not isinstance(routes, list) or not routes or not isinstance(routes[0], dict):
            return None
        geometry = routes[0].get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
            return None
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list):
            return None
        line = [_coord_pair(coord) for coord in coordinates]
        valid_line = [coord for coord in line if coord is not None]
        if len(valid_line) < 2 or not _short_route_is_reasonable(valid_line, start, end):
            return None
        return valid_line

    async def _pk_to_lonlat_candidates(self, road_ref: str, kilometer: float) -> list[list[float]]:
        cache_key = f"{road_ref}:{kilometer:g}"
        if cache_key in self._pk_point_cache:
            return self._pk_point_cache[cache_key]
        if self._pk_sample_budget is not None and self._pk_sample_budget <= 0:
            return []
        if self._pk_sample_budget is not None:
            self._pk_sample_budget -= 1
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    self.config.pk_to_xy_url,
                    params={"f": "json", "Carretera": road_ref, "Km": f"{kilometer:g}"},
                    headers={"User-Agent": "wildfire-intelligence-platform/0.1"},
                    timeout=self.config.pk_to_xy_timeout_seconds,
                )
            response.raise_for_status()
            payload = _dgt_json_payload(response.text)
        except (httpx.HTTPError, ValueError):
            self._pk_point_cache[cache_key] = []
            return []
        projected = _pk_xy_results(payload)
        candidates: list[list[float]] = []
        for x, y in projected:
            lonlat = await self._projected_to_lonlat(x, y)
            if lonlat is not None:
                candidates.append(lonlat)
        self._pk_point_cache[cache_key] = candidates
        return candidates

    async def _projected_to_lonlat(self, x: float, y: float) -> list[float] | None:
        result = await self.session.execute(
            select(
                func.ST_X(func.ST_Transform(func.ST_SetSRID(func.ST_Point(x, y), 25830), 4326)),
                func.ST_Y(func.ST_Transform(func.ST_SetSRID(func.ST_Point(x, y), 25830), 4326)),
            )
        )
        row = result.one_or_none()
        if row is None:
            return None
        lon = float(row[0])
        lat = float(row[1])
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            return None
        return [lon, lat]

    async def _local_road_geometry(
        self,
        road_ref: str,
        start: list[float],
        end: list[float],
        source_id: Any,
    ) -> MatchedRoadGeometry | None:
        west = min(start[0], end[0]) - 0.05
        east = max(start[0], end[0]) + 0.05
        south = min(start[1], end[1]) - 0.05
        north = max(start[1], end[1]) + 0.05
        envelope = func.ST_MakeEnvelope(west, south, east, north, 4326)
        result = await self.session.execute(
            select(func.ST_AsGeoJSON(RoadSegment.geometry))
            .where(
                RoadSegment.source_id != source_id,
                RoadSegment.road_ref == road_ref,
                func.ST_Intersects(RoadSegment.geometry, envelope),
            )
            .limit(220)
        )
        lines: list[list[list[float]]] = []
        matched_by_road_ref = True
        for geometry_json in result.scalars():
            if not geometry_json:
                continue
            geometry = json.loads(geometry_json)
            if geometry.get("type") != "LineString" or not isinstance(geometry.get("coordinates"), list):
                continue
            line = [_coord_pair(coord) for coord in geometry["coordinates"]]
            valid_line = [coord for coord in line if coord is not None]
            if len(valid_line) >= 2:
                lines.append(valid_line)
        if not lines:
            return None
        selected = _select_road_lines(lines, start, end)
        if not selected:
            return None
        strategy = "road_ref_network_match" if matched_by_road_ref else "road_network_proximity_match"
        return _matched_geometry(selected, strategy)

    async def _osrm_road_geometry(
        self,
        road_ref: str,
        start: list[float],
        end: list[float],
    ) -> MatchedRoadGeometry | None:
        if self._osrm_budget is not None and self._osrm_budget <= 0:
            return None
        if self._osrm_budget is not None:
            self._osrm_budget -= 1
        url = f"{self.config.osrm_route_url.rstrip('/')}/{start[0]},{start[1]};{end[0]},{end[1]}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    url,
                    params={"overview": "full", "geometries": "geojson", "steps": "true", "alternatives": "false"},
                    headers={"User-Agent": "wildfire-intelligence-platform/0.1"},
                    timeout=self.config.osrm_timeout_seconds,
                )
            if response.status_code in {429, 500, 502, 503, 504}:
                if self._osrm_budget is not None:
                    self._osrm_budget = 0
                return None
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        if payload.get("code") != "Ok":
            return None
        routes = payload.get("routes")
        if not isinstance(routes, list) or not routes:
            return None
        route = routes[0]
        if not isinstance(route, dict) or not _route_has_road_ref(route, road_ref):
            return None
        geometry = route.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") != "LineString":
            return None
        coordinates = geometry.get("coordinates")
        if not isinstance(coordinates, list):
            return None
        line = [_coord_pair(coord) for coord in coordinates]
        valid_line = [coord for coord in line if coord is not None]
        if len(valid_line) < 2 or not _route_is_reasonable(valid_line, start, end):
            return None
        return _matched_geometry([valid_line], "osrm_route_match")

    async def _overpass_road_geometry(
        self,
        road_ref: str,
        start: list[float],
        end: list[float],
    ) -> MatchedRoadGeometry | None:
        if self._overpass_budget <= 0:
            return None
        self._overpass_budget -= 1
        padding = min(max(_distance_degrees(start, end) * 0.35, 0.05), 0.25)
        west = min(start[0], end[0]) - padding
        east = max(start[0], end[0]) + padding
        south = min(start[1], end[1]) - padding
        north = max(start[1], end[1]) + padding
        ref_pattern = _overpass_ref_pattern(road_ref)
        query = f"""
[out:json][timeout:{self.config.overpass_timeout_seconds}];
(
  way["highway"]["ref"~"{ref_pattern}",i]({south},{west},{north},{east});
  way["highway"]["nat_ref"~"{ref_pattern}",i]({south},{west},{north},{east});
  way["highway"]["name"~"{ref_pattern}",i]({south},{west},{north},{east});
);
out tags geom 80;
"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.config.overpass_url,
                    data={"data": query},
                    headers={"User-Agent": "wildfire-intelligence-platform/0.1"},
                    timeout=self.config.overpass_timeout_seconds,
                )
            if response.status_code in {429, 500, 502, 503, 504}:
                self._overpass_budget = 0
                return None
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            return None
        lines: list[list[list[float]]] = []
        for element in payload.get("elements", []):
            if not isinstance(element, dict) or element.get("type") != "way":
                continue
            geometry = element.get("geometry")
            if not isinstance(geometry, list):
                continue
            line = []
            for point in geometry:
                if not isinstance(point, dict):
                    continue
                lon = point.get("lon")
                lat = point.get("lat")
                if isinstance(lon, int | float) and isinstance(lat, int | float):
                    line.append([float(lon), float(lat)])
            if len(line) >= 2:
                lines.append(line)
        selected = _select_ref_road_lines(lines, start, end)
        if not selected:
            return None
        return _matched_geometry(selected, "osm_overpass_road_ref_match")

    async def _request(self, url: str) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                if self.http_client is not None:
                    return await self.http_client.get(url, follow_redirects=True, timeout=self.config.timeout_seconds)
                async with httpx.AsyncClient() as client:
                    return await client.get(url, follow_redirects=True, timeout=self.config.timeout_seconds)
            except (httpx.TimeoutException, httpx.HTTPError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                await asyncio.sleep(min(2 ** (attempt - 1), 8))
        raise ValidationError(f"DATEX fetch failed: {last_error}")

    async def _get_or_create_source(self) -> DataSource:
        result = await self.session.execute(select(DataSource).where(DataSource.name == "NAP DATEX traffic restrictions"))
        source = result.scalar_one_or_none()
        if source is not None:
            source.base_url = ",".join(self.config.feed_urls)
            source.source_metadata = {"format": "DATEX II", "feeds": self.config.feed_urls}
            return source
        source = DataSource(
            name="NAP DATEX traffic restrictions",
            source_type=ProvenanceType.OFFICIAL,
            authority="DGT NAP / DGT / SCT / Trafikoa",
            base_url=",".join(self.config.feed_urls),
            license_name="Public NAP feeds; check per-feed licence",
            attribution="DGT NAP, SCT and traffic data owners",
            update_frequency="1-9 minutes depending on feed",
            expected_delay_seconds=300,
            reliability_score=0.9,
            source_metadata={"format": "DATEX II", "feeds": self.config.feed_urls},
        )
        self.session.add(source)
        await self.session.flush()
        return source

    async def _existing_hashes(self, hashes: list[str]) -> set[str]:
        if not hashes:
            return set()
        prefixed_hashes = [f"restriction:{item}" for item in hashes]
        result = await self.session.execute(
            select(RestrictionZone.deduplication_hash).where(RestrictionZone.deduplication_hash.in_(prefixed_hashes))
        )
        return {item.removeprefix("restriction:") for item in result.scalars() if item is not None}

    async def _reactivate_existing(self, record: DatexRestrictionRecord, source_id: Any, received_at: datetime) -> None:
        restriction_values: dict[str, Any] = {
            "expires_at": None,
            "name": record.title[:180],
            "restriction_type": record.kind[:120],
        }
        # A transient failure in the road-matching services must not flatten an
        # already enriched road route back to the two raw DATEX endpoints.
        if record.original_metadata.get("geometry_strategy") != "nap_datex_coordinates":
            restriction_values.update(
                original_metadata=record.original_metadata,
                geometry=WKTElement(record.geometry_wkt, srid=4326),
            )
        await self.session.execute(
            update(RestrictionZone)
            .where(RestrictionZone.deduplication_hash == f"restriction:{record.deduplication_hash}")
            .values(**restriction_values)
        )
        await self.session.execute(
            update(RoadIncident)
            .where(RoadIncident.deduplication_hash == f"incident:{record.deduplication_hash}")
            .values(expires_at=None, original_metadata=record.original_metadata, explanation=record.title)
        )
        result = await self.session.execute(
            select(RoadSegment.id)
            .where(RoadSegment.deduplication_hash.like(f"segment:{record.deduplication_hash}:%"))
            .order_by(RoadSegment.external_id)
        )
        existing_segment_ids = list(result.scalars())
        update_segment_geometry = record.original_metadata.get("geometry_strategy") != "nap_datex_coordinates"
        for index, segment_wkt in enumerate(record.segment_wkts):
            segment_hash = f"segment:{record.deduplication_hash}:{index}"
            values: dict[str, Any] = {
                "expires_at": None,
                "original_metadata": {**record.original_metadata, "segment_index": index},
                "name": record.title[:160],
                "road_ref": record.road_ref,
                "road_class": "nap_datex_affected_road",
            }
            if update_segment_geometry:
                values["geometry"] = WKTElement(segment_wkt, srid=4326)
            if index < len(existing_segment_ids):
                await self.session.execute(update(RoadSegment).where(RoadSegment.id == existing_segment_ids[index]).values(**values))
            else:
                self.session.add(
                    RoadSegment(
                        source_id=source_id,
                        external_id=f"{record.external_id}:segment:{index}",
                        provenance=ProvenanceType.OFFICIAL,
                        observed_at=record.observed_at,
                        received_at=received_at,
                        expires_at=record.expires_at,
                        verification_status=VerificationStatus.PENDING,
                        confidence=0.93,
                        original_metadata=values["original_metadata"],
                        deduplication_hash=segment_hash,
                        geometry=WKTElement(segment_wkt, srid=4326),
                        original_crs="EPSG:4326",
                        name=record.title[:160],
                        road_ref=record.road_ref,
                        road_class="nap_datex_affected_road",
                    )
                )
        for stale_segment_id in existing_segment_ids[len(record.segment_wkts) :]:
            await self.session.execute(update(RoadSegment).where(RoadSegment.id == stale_segment_id).values(expires_at=received_at))

    async def _expire_stale_records(self, source_id: Any, current_hashes: list[str], expires_at: datetime) -> None:
        current_restriction_hashes = [f"restriction:{item}" for item in current_hashes]
        current_incident_hashes = [f"incident:{item}" for item in current_hashes]
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
        await self.session.execute(update(RoadSegment).where(RoadSegment.source_id == source_id).values(expires_at=expires_at))

    def _road_incident_kind(self, kind: str) -> RoadIncidentKind:
        lowered = kind.lower()
        if "cortadas" in lowered or "restringida" in lowered:
            return RoadIncidentKind.OFFICIAL_CLOSURE
        if "lento" in lowered:
            return RoadIncidentKind.REDUCED_VISIBILITY
        return RoadIncidentKind.INSUFFICIENT_DATA

    def _hash(self, external_id: str, payload: dict[str, Any]) -> str:
        stable = f"{external_id}|{json.dumps(payload, sort_keys=True, default=str)}"
        return hashlib.sha256(stable.encode("utf-8")).hexdigest()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(root: ET.Element, local_name: str) -> list[ET.Element]:
    return [item for item in root.iter() if _local_name(item.tag) == local_name]


def _texts(root: ET.Element, local_name: str) -> list[str]:
    values = []
    for item in _children(root, local_name):
        if item.text and item.text.strip():
            values.append(item.text.strip())
    return values


def _text(root: ET.Element, local_name: str) -> str | None:
    values = _texts(root, local_name)
    return values[0] if values else None


def _first_text(root: ET.Element, local_names: list[str]) -> str | None:
    for local_name in local_names:
        value = _text(root, local_name)
        if value:
            return value
    return None


def _unique_texts(root: ET.Element, local_name: str) -> list[str]:
    seen: set[str] = set()
    values: list[str] = []
    for value in _texts(root, local_name):
        if value not in seen:
            seen.add(value)
            values.append(value)
    return values


def _coordinates(root: ET.Element) -> list[list[float]]:
    coords: list[list[float]] = []
    for point in _children(root, "pointCoordinates"):
        latitude = _text(point, "latitude")
        longitude = _text(point, "longitude")
        if latitude is None or longitude is None:
            continue
        try:
            coords.append([float(longitude), float(latitude)])
        except ValueError:
            continue
    return coords


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


def _distance_degrees(first: list[float], second: list[float]) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


def _line_point_distance(line: list[list[float]], point: list[float]) -> float:
    return min((_distance_degrees(coord, point) for coord in line), default=999)


def _line_length_degrees(line: list[list[float]]) -> float:
    return sum(_distance_degrees(line[index - 1], line[index]) for index in range(1, len(line)))


def _should_try_osrm(start: list[float], end: list[float]) -> bool:
    return 0.0005 <= _distance_degrees(start, end) <= 1.2


def _should_try_overpass(record: DatexRestrictionRecord, start: list[float], end: list[float]) -> bool:
    if not record.road_ref or _distance_degrees(start, end) > 1.2:
        return False
    return True


def _kilometer_bounds(record: DatexRestrictionRecord) -> tuple[float, float] | None:
    values: list[float] = []
    raw_points = record.original_metadata.get("kilometer_points")
    if isinstance(raw_points, list):
        for point in raw_points:
            try:
                values.append(float(str(point).replace(",", ".")))
            except ValueError:
                continue
    if len(values) < 2:
        raw_range = record.original_metadata.get("kilometer_range")
        if isinstance(raw_range, str):
            values = [float(match.replace(",", ".")) for match in re.findall(r"\d+(?:[.,]\d+)?", raw_range)]
    if len(values) < 2:
        return None
    return min(values), max(values)


def _should_try_pk_sampling(record: DatexRestrictionRecord, distance_km: float) -> bool:
    if distance_km <= 0 or distance_km > 90:
        return False
    cause = str(record.original_metadata.get("cause") or "").lower()
    record_type = str(record.original_metadata.get("record_type") or "").lower()
    kind = record.kind.lower()
    is_high_value = (
        "ambiental" in cause
        or "environment" in record_type
        or "incendi" in cause
        or "fire" in cause
        or "cortadas" in kind
        or "restringida" in kind
    )
    return is_high_value and distance_km >= 2


def _pk_sample_values(first_km: float, last_km: float, step_km: float) -> list[float]:
    step = max(step_km, 0.1)
    direction = 1 if last_km >= first_km else -1
    values = [first_km]
    current = first_km
    while abs(last_km - current) > step:
        current += step * direction
        values.append(round(current, 3))
    if values[-1] != last_km:
        values.append(last_km)
    return values


def _pk_xy_results(payload: dict[str, Any]) -> list[tuple[float, float]]:
    results = payload.get("results")
    if not isinstance(results, list):
        return []
    points: list[tuple[float, float]] = []
    for result in results:
        if not isinstance(result, dict) or result.get("paramName") != "localizacion":
            continue
        value = result.get("value")
        if not isinstance(value, list):
            continue
        for item in value:
            if not isinstance(item, list | tuple) or len(item) < 2:
                continue
            try:
                points.append((float(item[0]), float(item[1])))
            except (TypeError, ValueError):
                continue
    return points


def _dgt_json_payload(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        # The DGT geoprocessor emits zone codes such as '05' inside otherwise
        # valid JSON. Only normalize single-quoted scalar tokens.
        normalized = re.sub(r"'([^'\\]*)'", lambda match: json.dumps(match.group(1)), raw)
        payload = json.loads(normalized)
    if not isinstance(payload, dict):
        raise ValueError("DGT geoprocessor response must be an object")
    return payload


def _route_is_reasonable(line: list[list[float]], start: list[float], end: list[float]) -> bool:
    direct = _distance_degrees(start, end)
    if direct <= 0:
        return False
    route_length = _line_length_degrees(line)
    if route_length > max(direct * 35, direct + 0.35):
        return False
    return _line_point_distance(line, start) <= 0.05 and _line_point_distance(line, end) <= 0.05


def _short_route_is_reasonable(line: list[list[float]], start: list[float], end: list[float]) -> bool:
    direct = _distance_degrees(start, end)
    if direct <= 0:
        return False
    route_length = _line_length_degrees(line)
    if route_length > max(direct * 6, direct + 0.04):
        return False
    return _line_point_distance(line, start) <= 0.01 and _line_point_distance(line, end) <= 0.01


def _normalized_road_ref(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _normalized_road_ref_tokens(value: str | None) -> set[str]:
    if not value:
        return set()
    return {
        token
        for token in (_normalized_road_ref(part) for part in re.split(r"[,;/| ]+", value))
        if token
    }


def _route_has_road_ref(route: dict[str, Any], road_ref: str) -> bool:
    return _route_road_ref_share(route, road_ref) >= 0.55


def _route_road_ref_share(route: dict[str, Any], road_ref: str) -> float:
    target = _normalized_road_ref(road_ref)
    if not target:
        return 0
    legs = route.get("legs")
    if not isinstance(legs, list):
        return 0
    total_distance = 0.0
    matching_distance = 0.0
    for leg in legs:
        if not isinstance(leg, dict):
            continue
        steps = leg.get("steps")
        if not isinstance(steps, list):
            continue
        for step in steps:
            if not isinstance(step, dict):
                continue
            distance = float(step.get("distance") or 0)
            total_distance += max(distance, 0)
            candidates = [step.get("ref"), step.get("name")]
            if any(target in _normalized_road_ref_tokens(str(candidate)) for candidate in candidates if candidate is not None):
                matching_distance += max(distance, 0)
    if total_distance <= 0:
        return 0
    return matching_distance / total_distance


def _line_endpoint_score(line: list[list[float]], start: list[float], end: list[float]) -> float:
    forward = _distance_degrees(line[0], start) + _distance_degrees(line[-1], end)
    backward = _distance_degrees(line[-1], start) + _distance_degrees(line[0], end)
    if backward < forward:
        line.reverse()
        return backward
    return forward


def _select_road_lines(lines: list[list[list[float]]], start: list[float], end: list[float]) -> list[list[list[float]]]:
    scored = []
    for line in lines:
        score = min(_line_endpoint_score(line, start, end), _line_point_distance(line, start) + _line_point_distance(line, end))
        if score <= 0.09:
            scored.append((score, line))
    scored.sort(key=lambda item: item[0])
    return [line for _, line in scored[:24]]


def _select_ref_road_lines(lines: list[list[list[float]]], start: list[float], end: list[float]) -> list[list[list[float]]]:
    if not lines:
        return []
    midpoint = [(start[0] + end[0]) / 2, (start[1] + end[1]) / 2]
    span = _distance_degrees(start, end)
    max_distance = max(span * 1.8, 0.08)
    scored = []
    for line in lines:
        distance = min(_line_point_distance(line, start), _line_point_distance(line, end), _line_point_distance(line, midpoint))
        if distance <= max_distance:
            scored.append((distance, line))
    scored.sort(key=lambda item: item[0])
    return [line for _, line in scored[:80]]


def _multilinestring_wkt(lines: list[list[list[float]]]) -> str | None:
    parts = []
    for line in lines:
        points = [f"{coord[0]} {coord[1]}" for coord in line if len(coord) >= 2]
        if len(points) >= 2:
            parts.append(f"({', '.join(points)})")
    if not parts:
        return None
    return f"MULTILINESTRING({', '.join(parts)})"


def _road_graph_route(
    lines: list[list[list[float]]],
    start: list[float],
    end: list[float],
) -> list[list[float]] | None:
    if not lines:
        return None

    def node(point: list[float]) -> tuple[float, float]:
        return (round(point[0], 4), round(point[1], 4))

    graph: dict[tuple[float, float], list[tuple[float, tuple[float, float], list[list[float]]]]] = {}
    for line in lines:
        first, last = node(line[0]), node(line[-1])
        if first == last:
            continue
        weight = sum(_distance_degrees(left, right) for left, right in zip(line, line[1:], strict=False))
        graph.setdefault(first, []).append((weight, last, line))
        graph.setdefault(last, []).append((weight, first, list(reversed(line))))
    if not graph:
        return None

    start_node = min(graph, key=lambda candidate: _distance_degrees(list(candidate), start))
    end_node = min(graph, key=lambda candidate: _distance_degrees(list(candidate), end))
    distances = {start_node: 0.0}
    previous: dict[tuple[float, float], tuple[tuple[float, float], list[list[float]]]] = {}
    queue = [(0.0, start_node)]
    while queue:
        distance, current = heapq.heappop(queue)
        if distance != distances.get(current):
            continue
        if current == end_node:
            break
        for weight, neighbor, line in graph.get(current, []):
            candidate = distance + weight
            if candidate < distances.get(neighbor, math.inf):
                distances[neighbor] = candidate
                previous[neighbor] = (current, line)
                heapq.heappush(queue, (candidate, neighbor))
    if end_node not in distances:
        return None

    parts: list[list[list[float]]] = []
    current = end_node
    while current != start_node:
        parent, line = previous[current]
        parts.append(line)
        current = parent
    route: list[list[float]] = []
    for line in reversed(parts):
        route.extend(line if not route else line[1:])
    return route or None


def _matched_geometry(lines: list[list[list[float]]], strategy: str) -> MatchedRoadGeometry | None:
    segment_wkts = [wkt for line in lines if (wkt := linestring_wkt(line)) is not None]
    if not segment_wkts:
        return None
    geometry_wkt = segment_wkts[0] if len(segment_wkts) == 1 else _multilinestring_wkt(lines)
    if geometry_wkt is None:
        return None
    return MatchedRoadGeometry(geometry_wkt=geometry_wkt, segment_wkts=segment_wkts, strategy=strategy)


def _road_cache_key(road_ref: str, start: list[float], end: list[float]) -> str:
    rounded = [round(value, 3) for value in [*start, *end]]
    return f"{road_ref}:{rounded}"


def _overpass_ref_pattern(road_ref: str) -> str:
    escaped = re.escape(road_ref)
    return f"(^|;|,| )({escaped})($|;|,| )"


def _record_type(record: ET.Element) -> str:
    typed = record.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}type") or record.attrib.get("type")
    if typed:
        return typed.rsplit(":", 1)[-1]
    for candidate in ("roadMaintenanceType", "trafficConstrictionType", "accidentType", "mobilityType"):
        value = _text(record, candidate)
        if value:
            return value
    return _local_name(record.tag)


def _functional_category(record: ET.Element) -> str:
    values = " ".join(
        value
        for value in [
            _record_type(record),
            _text(record, "causeType"),
            _text(record, "detailedCauseType"),
            _text(record, "roadMaintenanceType"),
            _text(record, "roadOrCarriagewayOrLaneManagementType"),
            _text(record, "trafficConstrictionType"),
            _text(record, "mobilityType"),
            _text(record, "accidentType"),
        ]
        if value
    ).lower()
    if any(token in values for token in ("roadclosed", "road closed", "carriagewayclosed", "closed", "closure")):
        return "CARRETERAS CORTADAS"
    if any(token in values for token in ("slow", "congestion", "queue", "stationarytraffic", "heavilycongested")):
        return "TRÁFICO LENTO"
    if any(token in values for token in ("restriction", "restricted", "weightrestriction", "heightrestriction", "do not use", "narrowlanes")):
        return "CIRCULACIÓN RESTRINGIDA"
    if any(token in values for token in ("diversion", "detour", "rerouting", "holding", "embolsamiento")):
        return "DESVÍOS Y EMBOLSAMIENTOS"
    return "OTRAS AFECCIONES"


def _label(value: str | None, labels: dict[str, str]) -> str | None:
    if not value:
        return None
    return labels.get(value, value)


def _kilometer_range(points: list[str]) -> str | None:
    parsed: list[float] = []
    for point in points:
        try:
            parsed.append(float(point))
        except ValueError:
            continue
    if not parsed:
        return None
    start = min(parsed)
    end = max(parsed)
    if start == end:
        return f"PK {start:g}"
    return f"PK {start:g} - {end:g}"


def _datex_details(record: ET.Element) -> dict[str, Any]:
    cause_type = _text(record, "causeType")
    detailed_cause_type = _text(record, "detailedCauseType")
    road_maintenance_type = _text(record, "roadMaintenanceType")
    management_type = _text(record, "roadOrCarriagewayOrLaneManagementType")
    lane_usage = _text(record, "laneUsage")
    direction = _text(record, "tpegDirectionRoad") or _text(record, "tpegDirection")
    severity = _text(record, "severity")
    kilometers = _unique_texts(record, "kilometerPoint")
    municipalities = _unique_texts(record, "municipality")
    provinces = _unique_texts(record, "province")
    autonomous_communities = _unique_texts(record, "autonomousCommunity")
    cause = (
        _label(detailed_cause_type, DETAIL_LABELS)
        or _label(road_maintenance_type, DETAIL_LABELS)
        or _label(cause_type, CAUSE_LABELS)
        or _label(management_type, DETAIL_LABELS)
    )
    return {
        "cause_type": cause_type,
        "detailed_cause_type": detailed_cause_type,
        "cause": cause,
        "management_type": management_type,
        "lane_usage": lane_usage,
        "affected_lane": _label(lane_usage, LANE_LABELS),
        "direction": _label(direction, DIRECTION_LABELS),
        "service_level": _label(severity, SERVICE_LEVEL_LABELS),
        "severity": severity,
        "kilometer_points": kilometers,
        "kilometer_range": _kilometer_range(kilometers),
        "province": " - ".join(provinces) if provinces else None,
        "municipalities": " - ".join(municipalities) if municipalities else None,
        "autonomous_community": " - ".join(autonomous_communities) if autonomous_communities else None,
    }


def _title(record: ET.Element, record_type: str, road_ref: str | None, details: dict[str, Any]) -> str:
    comments = _texts(record, "value")
    if comments:
        return comments[0][:240]
    cause = details.get("cause") or _label(record_type, DETAIL_LABELS) or record_type
    road = road_ref or _text(record, "roadName")
    kilometer_range = details.get("kilometer_range")
    municipalities = details.get("municipalities")
    if road and kilometer_range:
        return f"{cause}: {road} ({kilometer_range})"
    if road:
        return f"{cause}: {road}"
    if municipalities:
        return f"{cause}: {municipalities}"
    if road_ref:
        return f"{record_type} a {road_ref}"
    return record_type


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
