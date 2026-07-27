from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Generic, TypeVar
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class Repository(Generic[ModelT]):
    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    async def add(self, entity: ModelT) -> ModelT:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def get(self, entity_id: UUID) -> ModelT | None:
        return await self.session.get(self.model, entity_id)

    async def list_active(self, limit: int = 100, offset: int = 0) -> Sequence[ModelT]:
        statement: Select[tuple[ModelT]] = select(self.model).limit(limit).offset(offset)
        if hasattr(self.model, "deleted_at"):
            statement = statement.where(self.model.deleted_at.is_(None))  # type: ignore[attr-defined]
        result = await self.session.execute(statement)
        return result.scalars().all()

    async def soft_delete(self, entity: ModelT) -> ModelT:
        if not hasattr(entity, "deleted_at"):
            raise TypeError(f"{type(entity).__name__} does not support soft delete")
        entity.deleted_at = datetime.now(UTC)
        await self.session.flush()
        return entity
