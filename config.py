"""云端遥测独立存储配置。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CloudTelemetryStorageConfig:
    """云端遥测独立存储配置。"""

    database_type: str = "sqlite"
    sqlite_path: str = "data/cloud_telemetry/cloud_telemetry.db"
    postgresql_host: str = "localhost"
    postgresql_port: int = 5432
    postgresql_database: str = "mofox_cloud_telemetry"
    postgresql_user: str = "postgres"
    postgresql_password: str = ""
    postgresql_schema: str = "cloud_telemetry"
    postgresql_ssl_mode: str = "prefer"
    postgresql_ssl_ca: str = ""
    postgresql_ssl_cert: str = ""
    postgresql_ssl_key: str = ""
    connection_pool_size: int = 10
    connection_timeout: int = 30
    echo: bool = False