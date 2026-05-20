"""云端遥测独立数据库管理。"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging
from pathlib import Path
from typing import Any, TypeVar
from urllib.parse import quote_plus

from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    close_all_sessions,
    create_async_engine,
)
from sqlalchemy.pool import NullPool
from sqlalchemy.schema import CreateColumn

from .config import CloudTelemetryStorageConfig
from .models import Base
from .persistence import CloudTelemetryCRUD, CloudTelemetryQuery

logger = logging.getLogger("cloud_telemetry_backend.database")

T = TypeVar("T")


class CloudTelemetryDatabase:
    """云端遥测独立数据库管理器。"""

    def __init__(self, config: CloudTelemetryStorageConfig) -> None:
        self._config = config
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    @property
    def config(self) -> CloudTelemetryStorageConfig:
        """返回数据库配置。"""

        return self._config

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """返回会话工厂。"""

        if self._session_factory is None:
            raise RuntimeError("云端遥测数据库尚未初始化")
        return self._session_factory

    async def initialize(self) -> None:
        """初始化独立数据库引擎与表结构。"""

        if self._engine is not None:
            return

        url, engine_kwargs = self._build_engine_args()
        engine = create_async_engine(url, **engine_kwargs)

        async with engine.begin() as conn:
            if self._config.database_type == "postgresql":
                schema = self._config.postgresql_schema.strip() or "public"
                if schema != "public":
                    await conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
                    await conn.execute(text(f'SET search_path TO "{schema}"'))
            await conn.run_sync(Base.metadata.create_all)
            if self._config.database_type == "sqlite":
                await self._apply_sqlite_additive_migrations(conn)

        self._engine = engine
        self._session_factory = async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        logger.info("云端遥测数据库初始化完成")

    async def close(self) -> None:
        """关闭数据库连接。"""

        if self._engine is None:
            return

        await close_all_sessions()
        await self._engine.dispose()
        self._engine = None
        self._session_factory = None

    def crud(self, model: type[T]) -> CloudTelemetryCRUD[T]:
        """返回绑定到云端遥测数据库的 CRUD 接口。"""

        return CloudTelemetryCRUD(model, session_factory=self.session_factory)

    def query(self, model: type[T]) -> CloudTelemetryQuery[T]:
        """返回绑定到云端遥测数据库的查询构建器。"""

        return CloudTelemetryQuery(model, session_factory=self.session_factory)

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """返回数据库会话上下文。"""

        async with self.session_factory() as session:
            yield session

    def _build_engine_args(self) -> tuple[str, dict[str, Any]]:
        """构建 SQLAlchemy 异步引擎参数。"""

        if self._config.database_type == "sqlite":
            sqlite_path = Path(self._config.sqlite_path)
            sqlite_path.parent.mkdir(parents=True, exist_ok=True)
            url = f"sqlite+aiosqlite:///{sqlite_path.absolute().as_posix()}"
            kwargs = {
                "echo": self._config.echo,
                "future": True,
                "poolclass": NullPool,
                "connect_args": {
                    "check_same_thread": False,
                    "timeout": self._config.connection_timeout,
                },
            }
            return url, kwargs

        if self._config.database_type != "postgresql":
            raise ValueError(f"不支持的云端遥测数据库类型: {self._config.database_type}")

        host = self._config.postgresql_host
        if host.lower() == "localhost":
            host = "127.0.0.1"

        encoded_user = quote_plus(self._config.postgresql_user)
        encoded_password = quote_plus(self._config.postgresql_password)
        url = (
            f"postgresql+asyncpg://{encoded_user}:{encoded_password}"
            f"@{host}:{self._config.postgresql_port}/{self._config.postgresql_database}"
        )
        connect_args: dict[str, Any] = {
            "timeout": self._config.connection_timeout,
            "command_timeout": max(60, self._config.connection_timeout * 2),
            "server_settings": {
                "search_path": self._config.postgresql_schema.strip() or "public",
            },
        }
        ssl_mode = self._config.postgresql_ssl_mode
        if ssl_mode == "disable":
            connect_args["ssl"] = False
        elif ssl_mode == "allow":
            connect_args["ssl"] = "allow"
        elif ssl_mode == "require":
            connect_args["ssl"] = True
        elif ssl_mode == "verify-ca":
            connect_args["ssl"] = True
            if self._config.postgresql_ssl_ca:
                connect_args["sslrootcert"] = self._config.postgresql_ssl_ca
        elif ssl_mode == "verify-full":
            connect_args["ssl"] = True
            if self._config.postgresql_ssl_ca:
                connect_args["sslrootcert"] = self._config.postgresql_ssl_ca
            if self._config.postgresql_ssl_cert:
                connect_args["sslcert"] = self._config.postgresql_ssl_cert
            if self._config.postgresql_ssl_key:
                connect_args["sslkey"] = self._config.postgresql_ssl_key

        kwargs = {
            "echo": self._config.echo,
            "future": True,
            "pool_size": self._config.connection_pool_size,
            "max_overflow": self._config.connection_pool_size * 2,
            "pool_timeout": self._config.connection_timeout,
            "pool_recycle": 1800,
            "pool_pre_ping": True,
            "connect_args": connect_args,
        }
        return url, kwargs

    async def _apply_sqlite_additive_migrations(self, conn: Any) -> None:
        """为已有 SQLite 表补齐可安全追加的新列。"""

        missing_columns = await conn.run_sync(self._collect_sqlite_missing_columns)
        if not missing_columns:
            return

        preparer = conn.dialect.identifier_preparer
        for table_name, columns in missing_columns.items():
            quoted_table = preparer.quote(table_name)
            for column in columns:
                column_ddl = str(CreateColumn(column).compile(dialect=conn.dialect)).strip()
                await conn.execute(
                    text(f"ALTER TABLE {quoted_table} ADD COLUMN {column_ddl}")
                )
                logger.info(
                    "SQLite schema updated: added column %s.%s",
                    table_name,
                    column.name,
                )

    def _collect_sqlite_missing_columns(self, sync_conn: Any) -> dict[str, list[Any]]:
        """收集 SQLite 已有表中缺失、且可用 ALTER TABLE 安全追加的列。"""

        inspector = inspect(sync_conn)
        existing_tables = set(inspector.get_table_names())
        missing_columns: dict[str, list[Any]] = {}

        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue

            existing_column_names = {
                column_info["name"] for column_info in inspector.get_columns(table.name)
            }
            safe_missing = [
                column
                for column in table.columns
                if column.name not in existing_column_names
                and self._is_safe_sqlite_additive_column(column)
            ]
            if safe_missing:
                missing_columns[table.name] = safe_missing

        return missing_columns

    def _is_safe_sqlite_additive_column(self, column: Any) -> bool:
        """判断列是否适合通过 SQLite ALTER TABLE 直接补齐。"""

        if column.primary_key or column.unique or column.foreign_keys:
            return False
        if column.server_default is not None:
            return True
        return bool(column.nullable)


_global_database: CloudTelemetryDatabase | None = None


async def init_cloud_telemetry_database(
    config: CloudTelemetryStorageConfig | None = None,
    **kwargs: Any,
) -> CloudTelemetryDatabase:
    """初始化全局云端遥测数据库管理器。"""

    global _global_database

    storage_config = config or CloudTelemetryStorageConfig(**kwargs)

    if _global_database is not None:
        if _global_database.config == storage_config:
            return _global_database
        await _global_database.close()
        _global_database = None

    database = CloudTelemetryDatabase(storage_config)
    await database.initialize()
    _global_database = database
    return database


def get_cloud_telemetry_database() -> CloudTelemetryDatabase:
    """返回全局云端遥测数据库管理器。"""

    if _global_database is None:
        raise RuntimeError("云端遥测数据库尚未初始化")
    return _global_database


async def close_cloud_telemetry_database() -> None:
    """关闭全局云端遥测数据库管理器。"""

    global _global_database

    if _global_database is None:
        return

    await _global_database.close()
    _global_database = None