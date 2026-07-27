from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Annotated, Any, Literal
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from geoalchemy2 import functions as geofunc
from sqlalchemy import Select, String, cast, desc, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.domain.enums import ProvenanceType
from app.domain.models import (
    ConfidenceAssessment,
    DataSource,
    EvacuationZone,
    FireDetection,
    FirePerimeter,
    Incident,
    IncidentVersion,
    OfficialNotice,
    RestrictionZone,
    RiskForecast,
    RoadIncident,
    RoadSegment,
    SmokeForecast,
)
from app.infrastructure.database import get_session
from app.infrastructure.redis import get_redis

router = APIRouter(prefix="/civil", tags=["civil"])

DEFAULT_LIMIT = 50
MAX_LIMIT = 200
ESTIMATE_CURRENT_WINDOW = timedelta(hours=12)
PUBLIC_CACHE_SECONDS = 30
RATE_LIMIT_PER_MINUTE = 180
IGN_MUNICIPALITIES_URL = "https://services1.arcgis.com/nCKYwcSONQTkPA4K/arcgis/rest/services/muni/FeatureServer/0/query"


@dataclass(frozen=True)
class CivilQuery:
    bbox: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    radius_meters: int | None = None
    municipality: str | None = None
    observed_from: datetime | None = None
    observed_to: datetime | None = None
    status_filter: str | None = None
    source: str | None = None
    min_confidence: float | None = None
    limit: int = DEFAULT_LIMIT
    offset: int = 0
    sort: str = "updated_desc"
    response_format: Literal["json", "geojson"] = "json"
    only_current: bool = True


def civil_query(
    bbox: str | None = Query(default=None, description="west,south,east,north in EPSG:4326"),
    latitude: float | None = Query(default=None, ge=-90, le=90),
    longitude: float | None = Query(default=None, ge=-180, le=180),
    radius_meters: int | None = Query(default=None, ge=1, le=250_000),
    municipality: str | None = Query(default=None, min_length=2, max_length=120),
    observed_from: datetime | None = None,
    observed_to: datetime | None = None,
    status_filter: str | None = Query(default=None, alias="status"),
    source: str | None = Query(default=None, min_length=2, max_length=120),
    min_confidence: float | None = Query(default=None, ge=0, le=1),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    sort: str = Query(default="updated_desc", pattern="^(updated_desc|observed_desc|confidence_desc)$"),
    response_format: Literal["json", "geojson"] = Query(default="json", alias="format"),
    only_current: bool = True,
) -> CivilQuery:
    if (latitude is None) ^ (longitude is None):
        raise HTTPException(status_code=422, detail="latitude and longitude must be provided together")
    if radius_meters is not None and latitude is None:
        raise HTTPException(status_code=422, detail="radius_meters requires latitude and longitude")
    return CivilQuery(
        bbox=bbox,
        latitude=latitude,
        longitude=longitude,
        radius_meters=radius_meters,
        municipality=municipality,
        observed_from=observed_from,
        observed_to=observed_to,
        status_filter=status_filter,
        source=source,
        min_confidence=min_confidence,
        limit=limit,
        offset=offset,
        sort=sort,
        response_format=response_format,
        only_current=only_current,
    )


async def rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    minute = datetime.now(UTC).strftime("%Y%m%d%H%M")
    key = f"civil:rate:{client}:{minute}"
    try:
        redis = get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 70)
        if count > RATE_LIMIT_PER_MINUTE:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Civil API rate limit exceeded",
            )
    except HTTPException:
        raise
    except Exception:
        return


CivilSession = Annotated[AsyncSession, Depends(get_session)]
CivilIfNoneMatch = Annotated[str | None, Header(alias="If-None-Match")]
CivilQueryDep = Annotated[CivilQuery, Depends(civil_query)]


def _parse_bbox(raw_bbox: str) -> tuple[float, float, float, float]:
    try:
        west, south, east, north = (float(value.strip()) for value in raw_bbox.split(","))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="bbox must be west,south,east,north") from exc
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90):
        raise HTTPException(status_code=422, detail="bbox coordinates are outside EPSG:4326 bounds")
    return west, south, east, north


def _jsonb_text(model: type[Any]) -> ColumnElement[str]:
    return cast(cast(model.original_metadata, JSONB), String)


def apply_spatial_filters(statement: Select[Any], model: type[Any], query: CivilQuery) -> Select[Any]:
    geometry = getattr(model, "geometry", None)
    if geometry is None:
        return statement
    if query.bbox:
        west, south, east, north = _parse_bbox(query.bbox)
        envelope = geofunc.ST_MakeEnvelope(west, south, east, north, 4326)
        statement = statement.where(geofunc.ST_Intersects(geometry, envelope))
    if query.radius_meters is not None and query.latitude is not None and query.longitude is not None:
        point = geofunc.ST_SetSRID(geofunc.ST_MakePoint(query.longitude, query.latitude), 4326)
        statement = statement.where(func.ST_DWithin(func.Geography(geometry), func.Geography(point), query.radius_meters))
    return statement


def _apply_common_filters(statement: Select[Any], model: type[Any], query: CivilQuery) -> Select[Any]:
    if query.observed_from is not None and hasattr(model, "observed_at"):
        statement = statement.where(model.observed_at >= query.observed_from)
    if query.observed_to is not None and hasattr(model, "observed_at"):
        statement = statement.where(model.observed_at <= query.observed_to)
    if query.status_filter and hasattr(model, "status"):
        statement = statement.where(cast(model.status, String) == query.status_filter)
    if query.source and hasattr(model, "source_id"):
        source_ids = select(DataSource.id).where(
            or_(
                DataSource.name.ilike(f"%{query.source}%"),
                DataSource.authority.ilike(f"%{query.source}%"),
            )
        )
        statement = statement.where(model.source_id.in_(source_ids))
    if query.min_confidence is not None and hasattr(model, "confidence"):
        statement = statement.where(model.confidence >= query.min_confidence)
    if query.municipality and hasattr(model, "original_metadata"):
        municipal_text = f"%{query.municipality}%"
        statement = statement.where(_jsonb_text(model).ilike(municipal_text))
    if query.only_current and hasattr(model, "provenance") and hasattr(model, "observed_at"):
        cutoff = datetime.now(UTC) - ESTIMATE_CURRENT_WINDOW
        statement = statement.where(
            or_(
                model.provenance != ProvenanceType.ESTIMATED,
                model.observed_at.is_(None),
                model.observed_at >= cutoff,
            )
        )
    if query.only_current and hasattr(model, "expires_at"):
        statement = statement.where(or_(model.expires_at.is_(None), model.expires_at > datetime.now(UTC)))
    statement = apply_spatial_filters(statement, model, query)
    sort_column = getattr(model, "updated_at", None)
    if query.sort == "observed_desc" and hasattr(model, "observed_at"):
        sort_column = model.observed_at
    if query.sort == "confidence_desc" and hasattr(model, "confidence"):
        sort_column = model.confidence
    if sort_column is not None:
        statement = statement.order_by(desc(sort_column).nullslast())
    return statement.offset(query.offset).limit(query.limit)


async def _latest_confidence(session: AsyncSession, resource_type: str, resource_id: UUID) -> ConfidenceAssessment | None:
    result = await session.execute(
        select(ConfidenceAssessment)
        .where(
            ConfidenceAssessment.resource_type == resource_type,
            ConfidenceAssessment.resource_id == resource_id,
        )
        .order_by(desc(ConfidenceAssessment.calculated_at))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _source(session: AsyncSession, source_id: UUID | None) -> DataSource | None:
    if source_id is None:
        return None
    return await session.get(DataSource, source_id)


def _age_seconds(record: Any) -> int | None:
    observed_at = getattr(record, "observed_at", None)
    if observed_at is None:
        return None
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    return max(0, int((datetime.now(UTC) - observed_at).total_seconds()))


def _is_old_estimate(record: Any) -> bool:
    if getattr(record, "provenance", None) != ProvenanceType.ESTIMATED:
        return False
    observed_at = getattr(record, "observed_at", None)
    if observed_at is None:
        return True
    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(tzinfo=UTC)
    return bool(datetime.now(UTC) - observed_at > ESTIMATE_CURRENT_WINDOW)


def _lineage(
    record: Any,
    data_type: str,
    source: DataSource | None,
    confidence: ConfidenceAssessment | None,
    extra_warnings: list[str] | None = None,
) -> dict[str, Any]:
    warnings = list(extra_warnings or [])
    if confidence:
        warnings.extend(confidence.warnings)
    if _is_old_estimate(record):
        warnings.append("old_estimate_not_current")
    public_confidence = confidence.confidence if confidence else getattr(record, "confidence", None)
    return {
        "id": str(record.id),
        "data_type": data_type,
        "source": {
            "name": source.name if source else None,
            "authority": source.authority if source else None,
            "url": source.base_url if source else getattr(record, "url", None),
            "attribution": source.attribution if source else None,
        },
        "observed_at": getattr(record, "observed_at", None),
        "updated_at": getattr(record, "updated_at", None),
        "age_seconds": _age_seconds(record),
        "confidence": public_confidence,
        "confidence_category": confidence.category if confidence else None,
        "provenance": str(getattr(record, "provenance", "")),
        "is_current": not _is_old_estimate(record),
        "warnings": sorted(set(warnings)),
    }


def _incident_properties(record: Incident) -> dict[str, Any]:
    return {"title": record.title, "status": str(record.status), "summary": record.summary}


def _detection_properties(record: FireDetection) -> dict[str, Any]:
    metadata = record.original_metadata if isinstance(record.original_metadata, dict) else {}

    def metadata_float(key: str) -> float | None:
        raw_value = metadata.get(key)
        if not isinstance(raw_value, str | int | float):
            return None
        try:
            value = float(raw_value)
        except ValueError:
            return None
        return value if value > 0 else None

    return {
        "incident_id": str(record.incident_id) if record.incident_id else None,
        "sensor": record.sensor,
        "satellite": record.satellite,
        "frp_mw": record.frp_mw,
        "latitude": record.latitude,
        "longitude": record.longitude,
        "scan_km": metadata_float("scan"),
        "track_km": metadata_float("track"),
    }


def _perimeter_properties(record: FirePerimeter) -> dict[str, Any]:
    return {
        "incident_id": str(record.incident_id),
        "area_hectares": record.area_hectares,
        "perimeter_kind": record.perimeter_kind,
    }


def _evacuation_properties(record: EvacuationZone) -> dict[str, Any]:
    return {
        "incident_id": str(record.incident_id) if record.incident_id else None,
        "name": record.name,
        "zone_kind": str(record.zone_kind),
        "instruction": record.instruction,
    }


def _restriction_properties(record: RestrictionZone) -> dict[str, Any]:
    metadata = record.original_metadata if isinstance(record.original_metadata, dict) else {}
    return {
        "incident_id": str(record.incident_id) if record.incident_id else None,
        "name": record.name,
        "zone_kind": str(record.zone_kind),
        "restriction_type": record.restriction_type,
        "cause": metadata.get("cause"),
        "road_ref": metadata.get("road_ref"),
        "kilometer_range": metadata.get("kilometer_range"),
        "affected_lane": metadata.get("affected_lane"),
        "direction": metadata.get("direction"),
        "service_level": metadata.get("service_level"),
        "province": metadata.get("province"),
        "municipalities": metadata.get("municipalities"),
        "validity_status": metadata.get("validity_status"),
        "geometry_strategy": metadata.get("geometry_strategy"),
    }


def _road_properties(record: RoadSegment) -> dict[str, Any]:
    return {
        "name": record.name,
        "road_ref": record.road_ref,
        "road_class": record.road_class,
        "surface": record.surface,
        "access": record.access,
    }


def _notice_properties(record: OfficialNotice) -> dict[str, Any]:
    return {
        "incident_id": str(record.incident_id) if record.incident_id else None,
        "title": record.title,
        "body": record.body,
        "url": record.url,
        "severity": record.severity,
    }


def _risk_properties(record: RiskForecast) -> dict[str, Any]:
    return {
        "incident_id": str(record.incident_id) if record.incident_id else None,
        "risk_type": record.risk_type,
        "risk_score": record.risk_score,
        "category": record.category,
    }


def _smoke_properties(record: SmokeForecast) -> dict[str, Any]:
    return {
        "incident_id": str(record.incident_id) if record.incident_id else None,
        "horizon_hours": record.horizon_hours,
        "intensity": record.intensity,
        "uncertainty": record.uncertainty,
        "visibility_impact": record.visibility_impact,
    }


async def _record_payload(
    session: AsyncSession,
    record: Any,
    data_type: str,
    properties: dict[str, Any],
    geometry: str | None = None,
    extra_warnings: list[str] | None = None,
) -> dict[str, Any]:
    source = await _source(session, getattr(record, "source_id", None))
    confidence = await _latest_confidence(session, data_type, record.id)
    payload = _lineage(record, data_type, source, confidence, extra_warnings)
    payload["properties"] = properties
    if geometry is not None:
        payload["geometry"] = json.loads(geometry)
    return payload


def _as_collection(items: list[dict[str, Any]], query: CivilQuery) -> dict[str, Any]:
    return {
        "data_type": "civil_collection",
        "items": items,
        "pagination": {"limit": query.limit, "offset": query.offset, "count": len(items)},
        "warnings": [],
    }


def _as_geojson(items: list[dict[str, Any]], query: CivilQuery) -> dict[str, Any]:
    features = []
    for item in items:
        feature = {
            "type": "Feature",
            "id": item["id"],
            "geometry": item.get("geometry"),
            "properties": {key: value for key, value in item.items() if key != "geometry"},
        }
        features.append(feature)
    return {
        "type": "FeatureCollection",
        "features": features,
        "pagination": {"limit": query.limit, "offset": query.offset, "count": len(items)},
    }


async def _public_response(
    request: Request,
    payload: dict[str, Any],
    if_none_match: str | None,
    cache_key: str,
) -> Response:
    try:
        cached = await get_redis().get(cache_key)
        if cached:
            cached_payload = json.loads(cached)
            etag = cached_payload["etag"]
            if if_none_match == etag:
                return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
            return JSONResponse(
                content=cached_payload["body"],
                headers={"ETag": etag, "Cache-Control": f"public, max-age={PUBLIC_CACHE_SECONDS}"},
            )
    except Exception:
        pass

    body = jsonable_encoder(payload)
    etag = sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
    try:
        await get_redis().setex(cache_key, PUBLIC_CACHE_SECONDS, json.dumps({"etag": etag, "body": body}))
    except Exception:
        pass
    return JSONResponse(
        content=body,
        headers={
            "ETag": etag,
            "Cache-Control": f"public, max-age={PUBLIC_CACHE_SECONDS}",
            "x-correlation-id": str(getattr(request.state, "correlation_id", "unknown")),
        },
    )


def _municipality_where(term: str) -> str:
    escaped = term.strip().replace("'", "''")
    return f"NAMEUNIT LIKE '%{escaped}%'"


async def _municipality_extent(client: httpx.AsyncClient, object_id: int) -> dict[str, float] | None:
    response = await client.get(
        IGN_MUNICIPALITIES_URL,
        params={
            "where": f"OBJECTID={object_id}",
            "returnExtentOnly": "true",
            "outSR": "4326",
            "f": "json",
        },
    )
    response.raise_for_status()
    extent = response.json().get("extent")
    if not extent:
        return None
    return {
        "west": float(extent["xmin"]),
        "south": float(extent["ymin"]),
        "east": float(extent["xmax"]),
        "north": float(extent["ymax"]),
    }


def _padded_bbox(extent: dict[str, float], padding_degrees: float = 0.03) -> str:
    west = max(-180, extent["west"] - padding_degrees)
    south = max(-90, extent["south"] - padding_degrees)
    east = min(180, extent["east"] + padding_degrees)
    north = min(90, extent["north"] + padding_degrees)
    return f"{west:.6f},{south:.6f},{east:.6f},{north:.6f}"


async def _list_records(
    request: Request,
    session: AsyncSession,
    query: CivilQuery,
    model: type[Any],
    data_type: str,
    properties_builder: Any,
    if_none_match: str | None,
) -> Response:
    geometry = getattr(model, "geometry", None)
    fields: tuple[Any, ...] = (model, func.ST_AsGeoJSON(geometry)) if geometry is not None else (model, None)
    statement = select(*[field for field in fields if field is not None])
    statement = _apply_common_filters(statement, model, query)
    result = await session.execute(statement)
    rows = result.all()
    items: list[dict[str, Any]] = []
    for row in rows:
        record = row[0]
        geometry_json = row[1] if geometry is not None else None
        items.append(
            await _record_payload(
                session,
                record,
                data_type,
                properties_builder(record),
                geometry_json,
            )
        )
    payload = _as_geojson(items, query) if query.response_format == "geojson" else _as_collection(items, query)
    return await _public_response(request, payload, if_none_match, f"civil:{request.url.path}?{request.url.query}")


@router.get("/incidents", dependencies=[Depends(rate_limit)])
async def list_incidents(
    request: Request,
    session: CivilSession,
    query: CivilQueryDep,
    if_none_match: CivilIfNoneMatch = None,
) -> Response:
    return await _list_records(request, session, query, Incident, "incident", _incident_properties, if_none_match)


@router.get("/incidents/{incident_id}", dependencies=[Depends(rate_limit)])
async def incident_detail(
    incident_id: UUID,
    request: Request,
    session: CivilSession,
    if_none_match: CivilIfNoneMatch = None,
) -> Response:
    result = await session.execute(select(Incident, func.ST_AsGeoJSON(Incident.geometry)).where(Incident.id == incident_id))
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="incident not found")
    payload = await _record_payload(session, row[0], "incident", _incident_properties(row[0]), row[1])
    return await _public_response(request, payload, if_none_match, f"civil:{request.url.path}?{request.url.query}")


@router.get("/incidents/{incident_id}/timeline", dependencies=[Depends(rate_limit)])
async def incident_timeline(
    incident_id: UUID,
    request: Request,
    session: CivilSession,
    if_none_match: CivilIfNoneMatch = None,
) -> Response:
    result = await session.execute(select(IncidentVersion).where(IncidentVersion.incident_id == incident_id).order_by(IncidentVersion.version.asc()))
    items = [
        {
            "id": str(version.id),
            "data_type": "incident_timeline",
            "observed_at": version.created_at,
            "updated_at": version.updated_at,
            "age_seconds": None,
            "confidence": None,
            "provenance": "official_or_observed_version",
            "is_current": True,
            "warnings": [],
            "properties": {
                "incident_id": str(version.incident_id),
                "version": version.version,
                "status": str(version.status),
                "title": version.title,
                "change_reason": version.change_reason,
            },
        }
        for version in result.scalars().all()
    ]
    payload = {"data_type": "civil_timeline", "items": items, "warnings": []}
    return await _public_response(request, payload, if_none_match, f"civil:{request.url.path}?{request.url.query}")


@router.get("/detections", dependencies=[Depends(rate_limit)])
async def list_detections(
    request: Request,
    session: CivilSession,
    query: CivilQueryDep,
    if_none_match: CivilIfNoneMatch = None,
) -> Response:
    return await _list_records(request, session, query, FireDetection, "fire_detection", _detection_properties, if_none_match)


@router.get("/perimeters", dependencies=[Depends(rate_limit)])
async def list_perimeters(
    request: Request,
    session: CivilSession,
    query: CivilQueryDep,
    if_none_match: CivilIfNoneMatch = None,
) -> Response:
    return await _list_records(request, session, query, FirePerimeter, "fire_perimeter", _perimeter_properties, if_none_match)


@router.get("/evacuations", dependencies=[Depends(rate_limit)])
async def list_evacuations(
    request: Request,
    session: CivilSession,
    query: CivilQueryDep,
    if_none_match: CivilIfNoneMatch = None,
) -> Response:
    return await _list_records(request, session, query, EvacuationZone, "evacuation_zone", _evacuation_properties, if_none_match)


@router.get("/restrictions", dependencies=[Depends(rate_limit)])
async def list_restrictions(
    request: Request,
    session: CivilSession,
    query: CivilQueryDep,
    if_none_match: CivilIfNoneMatch = None,
) -> Response:
    return await _list_records(request, session, query, RestrictionZone, "restriction_zone", _restriction_properties, if_none_match)


@router.get("/roads", dependencies=[Depends(rate_limit)])
async def list_roads(
    request: Request,
    session: CivilSession,
    query: CivilQueryDep,
    if_none_match: CivilIfNoneMatch = None,
) -> Response:
    return await _list_records(request, session, query, RoadSegment, "road_segment", _road_properties, if_none_match)


@router.get("/notices", dependencies=[Depends(rate_limit)])
async def list_notices(
    request: Request,
    session: CivilSession,
    query: CivilQueryDep,
    if_none_match: CivilIfNoneMatch = None,
) -> Response:
    return await _list_records(request, session, query, OfficialNotice, "official_notice", _notice_properties, if_none_match)


@router.get("/risk", dependencies=[Depends(rate_limit)])
async def list_risk(
    request: Request,
    session: CivilSession,
    query: CivilQueryDep,
    if_none_match: CivilIfNoneMatch = None,
) -> Response:
    return await _list_records(request, session, query, RiskForecast, "risk_forecast", _risk_properties, if_none_match)


@router.get("/smoke", dependencies=[Depends(rate_limit)])
async def list_smoke(
    request: Request,
    session: CivilSession,
    query: CivilQueryDep,
    if_none_match: CivilIfNoneMatch = None,
) -> Response:
    return await _list_records(request, session, query, SmokeForecast, "smoke_forecast", _smoke_properties, if_none_match)


@router.get("/search/geographic", dependencies=[Depends(rate_limit)])
async def geographic_search(
    request: Request,
    session: CivilSession,
    query: CivilQueryDep,
    if_none_match: CivilIfNoneMatch = None,
) -> Response:
    narrowed_query = CivilQuery(**{**query.__dict__, "limit": min(query.limit, 50), "response_format": "geojson"})
    return await _list_records(request, session, narrowed_query, Incident, "incident", _incident_properties, if_none_match)


@router.get("/search/municipality", dependencies=[Depends(rate_limit)])
async def municipality_search(
    request: Request,
    session: CivilSession,
    municipality: str = Query(min_length=2, max_length=120),
    if_none_match: CivilIfNoneMatch = None,
) -> Response:
    query = CivilQuery(municipality=municipality, limit=50, sort="updated_desc")
    return await _list_records(request, session, query, Incident, "incident", _incident_properties, if_none_match)


@router.get("/municipalities/search", dependencies=[Depends(rate_limit)])
async def municipality_lookup(
    request: Request,
    q: str = Query(min_length=2, max_length=120),
    limit: int = Query(default=8, ge=1, le=20),
    if_none_match: CivilIfNoneMatch = None,
) -> Response:
    cache_key = f"civil:{request.url.path}?{request.url.query}"
    try:
        cached = await get_redis().get(cache_key)
        if cached:
            cached_payload = json.loads(cached)
            etag = cached_payload["etag"]
            if if_none_match == etag:
                return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers={"ETag": etag})
            return JSONResponse(
                content=cached_payload["body"],
                headers={"ETag": etag, "Cache-Control": f"public, max-age={PUBLIC_CACHE_SECONDS}"},
            )
    except Exception:
        pass

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            IGN_MUNICIPALITIES_URL,
            params={
                "where": _municipality_where(q),
                "outFields": "OBJECTID,codine,NATCODE,NAMEUNIT,NATLEVNAME",
                "returnGeometry": "false",
                "returnCentroid": "true",
                "outSR": "4326",
                "f": "json",
                "resultRecordCount": str(limit),
            },
        )
        response.raise_for_status()
        features = response.json().get("features", [])
        municipalities: list[dict[str, Any]] = []
        normalized_query = q.strip().casefold()
        for feature in features:
            attributes = feature.get("attributes", {})
            centroid = feature.get("centroid", {})
            object_id = attributes.get("OBJECTID")
            if object_id is None or not centroid:
                continue
            extent = await _municipality_extent(client, int(object_id))
            if extent is None:
                continue
            name = str(attributes.get("NAMEUNIT") or "")
            municipalities.append(
                {
                    "id": str(object_id),
                    "name": name,
                    "ine_code": attributes.get("codine"),
                    "national_code": attributes.get("NATCODE"),
                    "longitude": float(centroid["x"]),
                    "latitude": float(centroid["y"]),
                    "bbox": _padded_bbox(extent),
                    "source": {
                        "name": "Municipios IGN",
                        "authority": "Instituto Geográfico Nacional",
                        "url": "https://www.ign.es",
                        "attribution": "Municipios IGN CC-BY 4.0 ign.es",
                    },
                    "match_rank": 0 if name.casefold() == normalized_query else 1 if name.casefold().startswith(normalized_query) else 2,
                }
            )
    municipalities.sort(key=lambda item: (item["match_rank"], item["name"]))
    payload = {
        "data_type": "municipality_lookup",
        "items": municipalities,
        "pagination": {"limit": limit, "offset": 0, "count": len(municipalities)},
        "warnings": [],
    }
    return await _public_response(request, payload, if_none_match, cache_key)


@router.get("/roads/incidents", dependencies=[Depends(rate_limit)])
async def list_road_incidents(
    request: Request,
    session: CivilSession,
    query: CivilQueryDep,
    if_none_match: CivilIfNoneMatch = None,
) -> Response:
    return await _list_records(
        request,
        session,
        query,
        RoadIncident,
        "road_incident",
        lambda record: {
            "road_segment_id": str(record.road_segment_id),
            "incident_id": str(record.incident_id) if record.incident_id else None,
            "kind": str(record.kind),
            "explanation": record.explanation,
        },
        if_none_match,
    )
