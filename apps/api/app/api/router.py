from fastapi import APIRouter

from app.api.routes.civil import router as civil_router
from app.api.routes.internal_ingestion import router as internal_ingestion_router
from app.api.routes.internal_quality import router as internal_quality_router
from app.api.routes.osint import router as osint_router
from app.api.routes.system import router as system_router

api_router = APIRouter()
api_router.include_router(system_router)
api_router.include_router(civil_router)
api_router.include_router(internal_ingestion_router)
api_router.include_router(internal_quality_router)
api_router.include_router(osint_router)
