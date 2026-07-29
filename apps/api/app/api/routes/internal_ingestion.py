from dataclasses import asdict
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models import DataIngestionRun, EmergencyPublication
from app.infrastructure.database import get_session
from app.ingestion.aemet import AemetConnector
from app.ingestion.aemet_alerts import AemetAlertsConnector
from app.ingestion.datex import DatexTrafficConnector
from app.ingestion.effis import EffisBurntAreasConnector
from app.ingestion.es_alert import EsAlertRecord, EsAlertRegistry
from app.ingestion.etraffic import DgtEtrafficConnector
from app.ingestion.firms import FirmsConnector
from app.ingestion.ign import IgnTransportConnector
from app.ingestion.osint import EmergencyOsintConnector, EmergencyOsintService, RawPublication, SourceSpec
from app.ingestion.osm import OsmRoadConnector
from app.ingestion.proteccio_civil import ProteccioCivilPlansConnector

router = APIRouter(prefix="/internal/ingestion", tags=["internal-ingestion"])


class FirmsReprocessRequest(BaseModel):
    raw_csv: str = Field(min_length=1)


class EsAlertPayload(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=240)
    instruction: str = Field(min_length=1, max_length=10_000)
    restriction_type: str = Field(default="public_safety", min_length=1, max_length=120)
    sent_at: datetime
    expires_at: datetime
    geometry: dict[str, object]
    authority: str = Field(min_length=1, max_length=160)
    level: str = Field(pattern="^(alert|prealert)$")
    area: str | None = Field(default=None, max_length=240)
    url: str | None = Field(default=None, max_length=2_000)
    is_test: bool = False


class EsAlertSyncRequest(BaseModel):
    source_generated_at: datetime
    complete_snapshot: bool = False
    allow_empty_snapshot: bool = False
    alerts: list[EsAlertPayload] = Field(max_length=5_000)


class OsintPublicationPayload(BaseModel):
    external_id: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=100_000)
    url: str = Field(min_length=1, max_length=4_000)
    published_at: datetime
    source_name: str = Field(min_length=1, max_length=180)
    authority: str = Field(min_length=1, max_length=180)
    source_type: str = Field(pattern="^(official|reliable_media|multiple_witnesses|individual)$")
    locations: list[str] = Field(default_factory=list, max_length=100)
    geometry: dict[str, object] | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class OsintIngestRequest(BaseModel):
    publications: list[OsintPublicationPayload] = Field(min_length=1, max_length=5_000)


class OsintReviewRequest(BaseModel):
    status: str = Field(pattern="^(accepted|rejected)$")
    notes: str = Field(min_length=3, max_length=4_000)
    reviewer_user_id: UUID | None = None


async def require_internal_token(x_internal_token: Annotated[str | None, Header()] = None) -> None:
    expected = get_settings().internal_api_token
    if not expected or x_internal_token != expected:
        raise HTTPException(status_code=404, detail="Not found")


@router.post("/firms/run", dependencies=[Depends(require_internal_token)])
async def run_firms_connector(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    result = await FirmsConnector(session).execute()
    return {
        "connector": result.connector_name,
        "status": result.status,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "metrics": asdict(result.metrics),
    }


@router.post("/effis/burnt-areas/run", dependencies=[Depends(require_internal_token)])
async def run_effis_burnt_areas_connector(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    result = await EffisBurntAreasConnector(session).execute()
    return {
        "connector": result.connector_name,
        "status": result.status,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "metrics": asdict(result.metrics),
    }


@router.post("/firms/reprocess", dependencies=[Depends(require_internal_token)])
async def reprocess_firms_connector(
    payload: FirmsReprocessRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    result = await FirmsConnector(session).execute_raw(payload.raw_csv)
    return {
        "connector": result.connector_name,
        "status": result.status,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "metrics": asdict(result.metrics),
    }


@router.post("/aemet/run", dependencies=[Depends(require_internal_token)])
async def run_aemet_connector(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    result = await AemetConnector(session).execute()
    return {
        "connector": result.connector_name,
        "status": result.status,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "metrics": asdict(result.metrics),
    }


@router.post("/aemet/alerts/run", dependencies=[Depends(require_internal_token)])
async def run_aemet_alerts_connector(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    result = await AemetAlertsConnector(session).execute()
    return {
        "connector": result.connector_name,
        "status": result.status,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "metrics": asdict(result.metrics),
    }


@router.post("/ign/transport/run", dependencies=[Depends(require_internal_token)])
async def run_ign_transport_connector(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    result = await IgnTransportConnector(session).execute()
    return {
        "connector": result.connector_name,
        "status": result.status,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "metrics": asdict(result.metrics),
    }


@router.post("/osm/roads/run", dependencies=[Depends(require_internal_token)])
async def run_osm_roads_connector(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    result = await OsmRoadConnector(session).execute()
    return {
        "connector": result.connector_name,
        "status": result.status,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "metrics": asdict(result.metrics),
    }


@router.post("/datex/traffic/run", dependencies=[Depends(require_internal_token)])
async def run_datex_traffic_connector(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    result = await DatexTrafficConnector(session).execute()
    return {
        "connector": result.connector_name,
        "status": result.status,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "metrics": asdict(result.metrics),
    }


@router.post("/datex/traffic/enrich", dependencies=[Depends(require_internal_token)])
async def enrich_datex_traffic_routes(
    session: Annotated[AsyncSession, Depends(get_session)],
    road_ref: str | None = Query(default=None, min_length=2, max_length=80),
) -> dict[str, int]:
    return await DatexTrafficConnector(session, unlimited_road_enrichment=True).enrich_pending_routes(
        limit=10,
        road_ref=road_ref,
    )


@router.post("/dgt/etraffic/run", dependencies=[Depends(require_internal_token)])
async def run_dgt_etraffic_connector(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    result = await DgtEtrafficConnector(session).execute()
    return {
        "connector": result.connector_name,
        "status": result.status,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "metrics": asdict(result.metrics),
    }


@router.post("/proteccio-civil/plans/run", dependencies=[Depends(require_internal_token)])
async def run_proteccio_civil_plans_connector(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    result = await ProteccioCivilPlansConnector(session).execute()
    return {
        "connector": result.connector_name,
        "status": result.status,
        "started_at": result.started_at,
        "finished_at": result.finished_at,
        "metrics": asdict(result.metrics),
    }


@router.post("/es-alert/sync", dependencies=[Depends(require_internal_token)])
async def sync_es_alert_restrictions(
    payload: EsAlertSyncRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    records = [
        EsAlertRecord(
            external_id=alert.external_id,
            title=alert.title,
            instruction=alert.instruction,
            restriction_type=alert.restriction_type,
            sent_at=alert.sent_at,
            expires_at=alert.expires_at,
            geometry=alert.geometry,
            authority=alert.authority,
            level=alert.level,
            area=alert.area,
            url=alert.url,
        )
        for alert in payload.alerts
        if not alert.is_test
    ]
    if payload.complete_snapshot and not records and not payload.allow_empty_snapshot:
        raise HTTPException(
            status_code=422,
            detail="Empty ES-Alert snapshot requires allow_empty_snapshot=true",
        )
    metrics = await EsAlertRegistry(session).sync(
        records,
        source_generated_at=payload.source_generated_at,
        complete_snapshot=payload.complete_snapshot,
    )
    return {"connector": EsAlertRegistry.name, "status": "completed", "metrics": asdict(metrics)}


@router.post("/osint/run", dependencies=[Depends(require_internal_token)])
async def run_emergency_osint_connector(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    result = await EmergencyOsintConnector(session).execute()
    return {"connector": result.connector_name, "status": result.status, "started_at": result.started_at,
            "finished_at": result.finished_at, "metrics": asdict(result.metrics)}


@router.post("/osint/publications", dependencies=[Depends(require_internal_token)])
async def ingest_emergency_osint_publications(
    payload: OsintIngestRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    records = [RawPublication(
        external_id=item.external_id, title=item.title, text=item.text, url=item.url,
        published_at=item.published_at, source=SourceSpec(item.source_name, item.authority, item.url,
        item.source_type, "normalized", reliability=1.0), locations=tuple(item.locations), geometry=item.geometry,
        starts_at=item.starts_at, ends_at=item.ends_at, metadata=item.metadata,
    ) for item in payload.publications]
    service = EmergencyOsintService(session)
    try:
        metrics = await service.ingest(records)
    finally:
        await service.close()
    return {"connector": "emergency_osint_normalized", "status": "completed", "metrics": asdict(metrics)}


@router.get("/osint/review", dependencies=[Depends(require_internal_token)])
async def emergency_osint_review_queue(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, object]:
    records = (await session.execute(select(EmergencyPublication).where(
        EmergencyPublication.review_status == "pending"
    ).order_by(desc(EmergencyPublication.published_at)).limit(limit))).scalars().all()
    return {"items": [{"id": str(item.id), "incident_id": str(item.incident_id) if item.incident_id else None,
            "title": item.title, "original_text": item.original_text, "url": item.url, "authority": item.authority,
            "event_type": item.event_type, "es_alert_status": item.es_alert_status, "locations": item.locations,
            "confidence": item.confidence, "published_at": item.published_at} for item in records], "count": len(records)}


@router.patch("/osint/review/{publication_id}", dependencies=[Depends(require_internal_token)])
async def review_emergency_osint_publication(
    publication_id: UUID,
    payload: OsintReviewRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    publication = await session.get(EmergencyPublication, publication_id)
    if publication is None:
        raise HTTPException(status_code=404, detail="Publication not found")
    publication.review_status = payload.status
    publication.review_notes = payload.notes
    publication.reviewed_by_user_id = payload.reviewer_user_id
    publication.reviewed_at = datetime.now(UTC)
    await session.commit()
    return {"id": str(publication.id), "review_status": publication.review_status, "reviewed_at": publication.reviewed_at}


@router.get("/firms/status", dependencies=[Depends(require_internal_token)])
async def firms_status(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    return await connector_status("nasa_firms", session)


@router.get("/{connector_name}/status", dependencies=[Depends(require_internal_token)])
async def named_connector_status(
    connector_name: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    allowed = {
        "aemet_opendata",
        "aemet_cap_alerts",
        "datex_traffic_restrictions",
        "dgt_etraffic_restrictions",
        "effis_burnt_areas",
        "emergency_osint",
        "es_alert_registry_sync",
        "ign_transport_features",
        "osm_overpass_roads",
        "nasa_firms",
        "nap_datex_traffic_restrictions",
        "proteccio_civil_active_plans",
    }
    if connector_name not in allowed:
        raise HTTPException(status_code=404, detail="Not found")
    return await connector_status(connector_name, session)


async def connector_status(connector_name: str, session: AsyncSession) -> dict[str, object]:
    result = await session.execute(
        select(DataIngestionRun)
        .where(DataIngestionRun.connector_name == connector_name)
        .order_by(desc(DataIngestionRun.started_at))
        .limit(5)
    )
    runs = result.scalars().all()
    return {
        "connector": connector_name,
        "runs": [
            {
                "id": str(run.id),
                "status": run.status.value,
                "started_at": run.started_at,
                "finished_at": run.finished_at,
                "received": run.received_count,
                "duplicates": run.duplicate_count,
                "persisted": run.persisted_count,
                "raw_object_uri": run.raw_object_uri,
            }
            for run in runs
        ],
    }
