from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.domain.models import DataIngestionRun
from app.infrastructure.database import get_session
from app.ingestion.aemet import AemetConnector
from app.ingestion.datex import DatexTrafficConnector
from app.ingestion.etraffic import DgtEtrafficConnector
from app.ingestion.firms import FirmsConnector
from app.ingestion.ign import IgnTransportConnector
from app.ingestion.osm import OsmRoadConnector
from app.ingestion.proteccio_civil import ProteccioCivilPlansConnector

router = APIRouter(prefix="/internal/ingestion", tags=["internal-ingestion"])


class FirmsReprocessRequest(BaseModel):
    raw_csv: str = Field(min_length=1)


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
        "datex_traffic_restrictions",
        "dgt_etraffic_restrictions",
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
