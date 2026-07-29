from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

TRAFFIC_INGESTION_LOCK_ID = 1_947_305_611


async def try_acquire_traffic_ingestion_lock(session: AsyncSession) -> bool:
    """Hold a transaction-scoped lock until the ingestion commits or rolls back."""
    result = await session.execute(select(func.pg_try_advisory_xact_lock(TRAFFIC_INGESTION_LOCK_ID)))
    return bool(result.scalar_one())
