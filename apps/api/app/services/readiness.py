import asyncio

from app.infrastructure.database import check_database
from app.infrastructure.object_storage import check_object_storage
from app.infrastructure.redis import check_redis
from app.schemas.system import ReadyResponse


async def collect_readiness() -> ReadyResponse:
    database, redis, object_storage = await asyncio.gather(
        check_database(),
        check_redis(),
        asyncio.to_thread(check_object_storage),
    )
    checks = {
        "database_postgis": database,
        "redis": redis,
        "object_storage": object_storage,
    }
    status = "ready" if all(checks.values()) else "not_ready"
    return ReadyResponse(status=status, checks=checks)
