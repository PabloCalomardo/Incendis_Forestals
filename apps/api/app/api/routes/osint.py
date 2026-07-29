from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import IncidentStatus
from app.domain.models import DataSource, EmergencyPublication, Incident
from app.infrastructure.database import get_session

router = APIRouter(prefix="/civil/osint", tags=["civil-osint"])
Session = Annotated[AsyncSession, Depends(get_session)]
TWITTER_VIEWER_PROFILE_URL = "https://twitterviewer.net/twitter-profile-viewer"
TWITTER_VIEWER_TERMS_URL = "https://twitterviewer.net/terms-of-service"


def _duration_seconds(metadata: dict[str, Any], now: datetime) -> int | None:
    raw_start = metadata.get("restriction_started_at")
    if not isinstance(raw_start, str):
        return None
    try:
        start = datetime.fromisoformat(raw_start)
        raw_end = metadata.get("ended_at")
        end = datetime.fromisoformat(raw_end) if isinstance(raw_end, str) else now
        return max(0, int((end - start).total_seconds()))
    except ValueError:
        return None


async def _publication_payload(session: AsyncSession, publication: EmergencyPublication) -> dict[str, Any]:
    source = await session.get(DataSource, publication.source_id)
    geometry = await session.scalar(select(func.ST_AsGeoJSON(EmergencyPublication.geometry)).where(EmergencyPublication.id == publication.id))
    return {
        "id": str(publication.id),
        "incident_id": str(publication.incident_id) if publication.incident_id else None,
        "event_type": publication.event_type,
        "risk_type": publication.risk_type,
        "action_state": publication.action_state,
        "es_alert_status": publication.es_alert_status,
        "title": publication.title,
        "authority": publication.authority,
        "published_at": publication.published_at,
        "starts_at": publication.starts_at,
        "ends_at": publication.ends_at,
        "instructions": publication.instructions,
        "es_alert_message": publication.es_alert_message,
        "locations": publication.locations,
        "original_text": publication.original_text,
        "url": publication.url,
        "source_type": publication.source_type,
        "source_name": source.name if source else None,
        "confidence": publication.confidence,
        "evidence_rank": publication.evidence_rank,
        "review_status": publication.review_status,
        "geometry": json.loads(geometry) if geometry else None,
        "geometry_inference_method": publication.geometry_inference_method,
        "spatial_precision": publication.spatial_precision,
    }


@router.get("/incidents")
async def list_osint_incidents(
    session: Session,
    window_hours: int = Query(default=24, ge=1, le=24 * 30),
    active_or_recent: bool = True,
    response_format: Literal["json", "geojson"] = Query(default="json", alias="format"),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    now = datetime.now(UTC)
    cutoff = now - timedelta(hours=window_hours)
    statement = select(Incident, func.ST_AsGeoJSON(Incident.geometry)).where(
        Incident.original_metadata["osint"].as_boolean().is_(True),
        Incident.original_metadata["merged_into"].astext.is_(None),
        func.coalesce(Incident.original_metadata["hidden"].as_boolean(), False).is_(False),
    )
    if active_or_recent:
        statement = statement.where(or_(Incident.status == IncidentStatus.ACTIVE, Incident.observed_at >= cutoff))
    rows = (await session.execute(statement.order_by(desc(Incident.observed_at)).limit(limit))).all()
    items: list[dict[str, Any]] = []
    for incident, geometry in rows:
        publications = (
            (
                await session.execute(
                    select(EmergencyPublication)
                    .where(
                        EmergencyPublication.incident_id == incident.id,
                        EmergencyPublication.review_status != "rejected",
                    )
                    .order_by(EmergencyPublication.published_at.asc())
                )
            )
            .scalars()
            .all()
        )
        evidence = [await _publication_payload(session, publication) for publication in publications]
        metadata = incident.original_metadata if isinstance(incident.original_metadata, dict) else {}
        item = {
            "id": str(incident.id),
            "title": incident.title,
            "summary": incident.summary,
            "status": str(incident.status),
            "risk_type": metadata.get("risk_type"),
            "event_type": metadata.get("event_type"),
            "es_alert_status": metadata.get("es_alert_status", "not_applicable"),
            "es_alert_message": metadata.get("es_alert_message"),
            "instructions": metadata.get("instructions"),
            "affected_locations": metadata.get("affected_locations", []),
            "started_at": metadata.get("restriction_started_at"),
            "ended_at": metadata.get("ended_at"),
            "duration_seconds": _duration_seconds(metadata, now),
            "confidence": incident.confidence,
            "observed_at": incident.observed_at,
            "sources": [
                {
                    "authority": entry["authority"],
                    "name": entry["source_name"],
                    "url": entry["url"],
                    "source_type": entry["source_type"],
                    "confidence": entry["confidence"],
                }
                for entry in evidence
            ],
            "timeline": evidence,
            "geometry": json.loads(geometry) if geometry else None,
        }
        items.append(item)
    if response_format == "geojson":
        return {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "id": item["id"], "geometry": item.pop("geometry"), "properties": item} for item in items],
            "metadata": {"window_hours": window_hours, "generated_at": now},
        }
    return {"data_type": "emergency_osint_incidents", "items": items, "pagination": {"limit": limit, "count": len(items)}, "generated_at": now}


@router.get("/incidents/{incident_id}")
async def osint_incident_detail(incident_id: UUID, session: Session) -> dict[str, Any]:
    incident = await session.get(Incident, incident_id)
    metadata = incident.original_metadata if incident and isinstance(incident.original_metadata, dict) else {}
    if incident is None or not (bool(metadata.get("osint")) or bool(metadata.get("canonical_fire"))):
        raise HTTPException(status_code=404, detail="Canonical incident not found")
    publications = (
        (
            await session.execute(
                select(EmergencyPublication)
                .where(
                    EmergencyPublication.incident_id == incident_id,
                    EmergencyPublication.review_status != "rejected",
                )
                .order_by(EmergencyPublication.published_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "id": str(incident.id),
        "title": incident.title,
        "summary": incident.summary,
        "status": str(incident.status),
        "confidence": incident.confidence,
        "duration_seconds": _duration_seconds(metadata, datetime.now(UTC)),
        "properties": metadata,
        "timeline": [await _publication_payload(session, item) for item in publications],
    }


@router.get("/review-queue")
async def public_review_queue_summary(session: Session) -> dict[str, int]:
    pending = await session.scalar(select(func.count(EmergencyPublication.id)).where(EmergencyPublication.review_status == "pending"))
    return {"pending": int(pending or 0)}


@router.get("/x-accounts")
async def institutional_x_accounts() -> dict[str, Any]:
    path = Path(__file__).parents[2] / "ingestion" / "osint_x_accounts.json"
    accounts = json.loads(path.read_text(encoding="utf-8"))
    return {
        "data_type": "institutional_x_accounts",
        "primary_gateway": "nitter",
        "nitter_base_url": "https://nitter.net",
        "collection_mode": "human_review",
        "automated_collection": False,
        "reason": "TwitterViewer terms prohibit automated scraping and bulk data collection.",
        "viewer_url": TWITTER_VIEWER_PROFILE_URL,
        "terms_url": TWITTER_VIEWER_TERMS_URL,
        "items": [
            {
                **account,
                "x_url": f"https://x.com/{account['handle']}",
                "nitter_url": f"https://nitter.net/{account['handle']}",
                "viewer_url": TWITTER_VIEWER_PROFILE_URL,
                "viewer_input": f"@{account['handle']}",
            }
            for account in accounts
        ],
    }
