from fastapi import APIRouter, Response, status

from app.core.config import get_settings
from app.schemas.system import HealthResponse, ReadyResponse, VersionResponse
from app.services.readiness import collect_readiness

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", response_model=ReadyResponse)
async def ready(response: Response) -> ReadyResponse:
    readiness = await collect_readiness()
    if readiness.status != "ready":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return readiness


@router.get("/version", response_model=VersionResponse)
async def version() -> VersionResponse:
    settings = get_settings()
    return VersionResponse(
        name=settings.project_name,
        version=settings.api_version,
        environment=settings.environment,
    )
