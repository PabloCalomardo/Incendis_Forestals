from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes.internal_ingestion import require_internal_token
from app.infrastructure.database import get_session
from app.services.quality import QualityPersistenceService

router = APIRouter(prefix="/internal/quality", tags=["internal-quality"])


@router.post("/run", dependencies=[Depends(require_internal_token)])
async def run_quality_pipeline(
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = 200,
) -> dict[str, object]:
    result = await QualityPersistenceService(session).run(limit=limit)
    return {"status": "completed", "metrics": result}


@router.get("/trace/{resource_type}/{resource_id}", dependencies=[Depends(require_internal_token)])
async def inspect_trace(
    resource_type: str,
    resource_id: UUID,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict[str, object]:
    trace = await QualityPersistenceService(session).trace(resource_type, resource_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Not found")
    return trace
