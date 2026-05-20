"""云端遥测后端内部数据库辅助。"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.sql import Select

T = TypeVar("T")


class CloudTelemetryCRUD(Generic[T]):
    """最小 CRUD 辅助。"""

    def __init__(
        self,
        model: type[T],
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._model = model
        self._session_factory = session_factory

    async def create(self, values: dict[str, object]) -> T:
        """创建一条记录。"""

        async with self._session_factory() as session:
            instance = self._model(**values)
            session.add(instance)
            await session.commit()
            await session.refresh(instance)
            return instance

    async def count(self) -> int:
        """返回记录总数。"""

        async with self._session_factory() as session:
            result = await session.execute(
                select(func.count()).select_from(self._model)
            )
            return int(result.scalar_one())


class CloudTelemetryQuery(Generic[T]):
    """最小查询构建器。"""

    def __init__(
        self,
        model: type[T],
        session_factory: async_sessionmaker[AsyncSession],
        statement: Select[tuple[T]] | None = None,
    ) -> None:
        self._model = model
        self._session_factory = session_factory
        self._statement = statement if statement is not None else select(model)

    def filter(self, **conditions: object) -> "CloudTelemetryQuery[T]":
        """按等值条件过滤。"""

        statement = self._statement
        for field_name, value in conditions.items():
            statement = statement.where(getattr(self._model, field_name) == value)
        return CloudTelemetryQuery(self._model, self._session_factory, statement)

    def order_by(self, *field_names: str) -> "CloudTelemetryQuery[T]":
        """按字段排序。"""

        ordering: list[object] = []
        for field_name in field_names:
            descending = field_name.startswith("-")
            resolved_name = field_name[1:] if descending else field_name
            column = getattr(self._model, resolved_name)
            ordering.append(column.desc() if descending else column.asc())
        statement = self._statement.order_by(*ordering)
        return CloudTelemetryQuery(self._model, self._session_factory, statement)

    async def first(self) -> T | None:
        """返回第一条记录。"""

        async with self._session_factory() as session:
            result = await session.execute(self._statement)
            return result.scalars().first()

    async def all(self) -> Sequence[T]:
        """返回全部记录。"""

        async with self._session_factory() as session:
            result = await session.execute(self._statement)
            return result.scalars().all()