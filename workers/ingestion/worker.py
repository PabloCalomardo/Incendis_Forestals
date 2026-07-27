from app.infrastructure.database import get_session_factory
from app.ingestion.aemet import AemetConnector
from app.ingestion.datex import DatexTrafficConnector
from app.ingestion.etraffic import DgtEtrafficConnector
from app.ingestion.firms import FirmsConnector
from app.ingestion.ign import IgnTransportConnector
from app.ingestion.osm import OsmRoadConnector
from app.ingestion.proteccio_civil import ProteccioCivilPlansConnector
from shared.celery_app import create_celery_app

celery_app = create_celery_app("ingestion", "ingestion")


@celery_app.task(name="ingestion.ping")  # type: ignore[misc]
def ping() -> dict[str, str]:
    return {"worker": "ingestion", "status": "ok"}


@celery_app.task(name="ingestion.run_firms")  # type: ignore[misc]
def run_firms() -> dict[str, object]:
    import asyncio

    async def _run() -> dict[str, object]:
        async with get_session_factory()() as session:
            result = await FirmsConnector(session).execute()
            return {
                "connector": result.connector_name,
                "status": result.status,
                "received": result.metrics.received,
                "duplicates": result.metrics.duplicated,
                "persisted": result.metrics.persisted,
            }

    return asyncio.run(_run())


@celery_app.task(name="ingestion.run_aemet")  # type: ignore[misc]
def run_aemet() -> dict[str, object]:
    import asyncio

    async def _run() -> dict[str, object]:
        async with get_session_factory()() as session:
            result = await AemetConnector(session).execute()
            return {
                "connector": result.connector_name,
                "status": result.status,
                "received": result.metrics.received,
                "duplicates": result.metrics.duplicated,
                "persisted": result.metrics.persisted,
            }

    return asyncio.run(_run())


@celery_app.task(name="ingestion.run_ign_transport")  # type: ignore[misc]
def run_ign_transport() -> dict[str, object]:
    import asyncio

    async def _run() -> dict[str, object]:
        async with get_session_factory()() as session:
            result = await IgnTransportConnector(session).execute()
            return {
                "connector": result.connector_name,
                "status": result.status,
                "received": result.metrics.received,
                "duplicates": result.metrics.duplicated,
                "persisted": result.metrics.persisted,
            }

    return asyncio.run(_run())


@celery_app.task(name="ingestion.run_osm_roads")  # type: ignore[misc]
def run_osm_roads() -> dict[str, object]:
    import asyncio

    async def _run() -> dict[str, object]:
        async with get_session_factory()() as session:
            result = await OsmRoadConnector(session).execute()
            return {
                "connector": result.connector_name,
                "status": result.status,
                "received": result.metrics.received,
                "duplicates": result.metrics.duplicated,
                "persisted": result.metrics.persisted,
            }

    return asyncio.run(_run())


@celery_app.task(name="ingestion.run_datex_traffic")  # type: ignore[misc]
def run_datex_traffic() -> dict[str, object]:
    import asyncio

    async def _run() -> dict[str, object]:
        async with get_session_factory()() as session:
            result = await DatexTrafficConnector(session).execute()
            return {
                "connector": result.connector_name,
                "status": result.status,
                "received": result.metrics.received,
                "duplicates": result.metrics.duplicated,
                "persisted": result.metrics.persisted,
            }

    return asyncio.run(_run())


@celery_app.task(name="ingestion.enrich_datex_roads")  # type: ignore[misc]
def enrich_datex_roads() -> dict[str, int]:
    import asyncio

    async def _run() -> dict[str, int]:
        async with get_session_factory()() as session:
            connector = DatexTrafficConnector(session, unlimited_road_enrichment=True)
            return await connector.enrich_pending_routes(limit=10)

    return asyncio.run(_run())


@celery_app.task(name="ingestion.run_dgt_etraffic")  # type: ignore[misc]
def run_dgt_etraffic() -> dict[str, object]:
    import asyncio

    async def _run() -> dict[str, object]:
        async with get_session_factory()() as session:
            result = await DgtEtrafficConnector(session).execute()
            return {
                "connector": result.connector_name,
                "status": result.status,
                "received": result.metrics.received,
                "duplicates": result.metrics.duplicated,
                "persisted": result.metrics.persisted,
            }

    return asyncio.run(_run())


@celery_app.task(name="ingestion.run_proteccio_civil_plans")  # type: ignore[misc]
def run_proteccio_civil_plans() -> dict[str, object]:
    import asyncio

    async def _run() -> dict[str, object]:
        async with get_session_factory()() as session:
            result = await ProteccioCivilPlansConnector(session).execute()
            return {
                "connector": result.connector_name,
                "status": result.status,
                "received": result.metrics.received,
                "duplicates": result.metrics.duplicated,
                "persisted": result.metrics.persisted,
            }

    return asyncio.run(_run())
