from app.infrastructure.database import get_session_factory
from app.services.quality import QualityPersistenceService
from shared.celery_app import create_celery_app

celery_app = create_celery_app("geospatial", "geospatial")


@celery_app.task(name="geospatial.ping")  # type: ignore[misc]
def ping() -> dict[str, str]:
    return {"worker": "geospatial", "status": "ok"}


@celery_app.task(name="geospatial.run_quality_pipeline")  # type: ignore[misc]
def run_quality_pipeline(limit: int = 200) -> dict[str, object]:
    import asyncio

    async def _run() -> dict[str, object]:
        async with get_session_factory()() as session:
            result = await QualityPersistenceService(session).run(limit=limit)
            return {"worker": "geospatial", "status": "ok", **result}

    return asyncio.run(_run())
