"""云端遥测独立后端配置。"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Mapping

from .config import CloudTelemetryStorageConfig


def _parse_bool(raw_value: str | None, *, default: bool) -> bool:
    """解析布尔环境变量。"""

    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(raw_value: str | None, *, default: int) -> int:
    """解析整型环境变量。"""

    if raw_value is None or not raw_value.strip():
        return default
    return int(raw_value)


def _parse_float(raw_value: str | None, *, default: float) -> float:
    """解析浮点型环境变量。"""

    if raw_value is None or not raw_value.strip():
        return default
    return float(raw_value)


def _parse_csv(raw_value: str | None) -> tuple[str, ...]:
    """解析逗号分隔字符串。"""

    if raw_value is None or not raw_value.strip():
        return ()
    return tuple(item.strip() for item in raw_value.split(",") if item.strip())


def _default_geoip_database_path() -> str:
    """Return the repo-root GeoLite2 database path when it exists."""

    candidate = Path(__file__).resolve().parent.parent / "GeoLite2-City.mmdb"
    if candidate.exists():
        return str(candidate)
    return ""


@dataclass(slots=True)
class CloudTelemetryBackendSettings:
    """云端遥测独立后端配置。"""

    app_name: str = "Cloud Telemetry Backend"
    ingest_prefix: str = "/_cloud_telemetry"
    host: str = "127.0.0.1"
    port: int = 8765
    admin_api_keys: tuple[str, ...] = ()
    default_heartbeat_interval_seconds: int = 300
    challenge_ttl_seconds: int = 300
    install_credential_ttl_seconds: int = 30 * 86400
    max_request_body_bytes: int = 262144
    rate_limit_window_seconds: int = 60
    ip_rate_limit_per_window: int = 120
    credential_rate_limit_per_window: int = 120
    registration_failure_limit: int = 5
    registration_failure_cooldown_seconds: int = 300
    offline_grace_factor: float = 2.0
    offline_scan_interval_seconds: float = 30.0
    gap_recovery_window: int = 50
    instance_detail_max_windows: int = 50
    instance_detail_max_diagnostic_events: int = 50
    geoip_database_path: str = _default_geoip_database_path()
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

    def to_storage_config(self) -> CloudTelemetryStorageConfig:
        """转换为存储配置。"""

        return CloudTelemetryStorageConfig(
            database_type=self.database_type,
            sqlite_path=self.sqlite_path,
            postgresql_host=self.postgresql_host,
            postgresql_port=self.postgresql_port,
            postgresql_database=self.postgresql_database,
            postgresql_user=self.postgresql_user,
            postgresql_password=self.postgresql_password,
            postgresql_schema=self.postgresql_schema,
            postgresql_ssl_mode=self.postgresql_ssl_mode,
            postgresql_ssl_ca=self.postgresql_ssl_ca,
            postgresql_ssl_cert=self.postgresql_ssl_cert,
            postgresql_ssl_key=self.postgresql_ssl_key,
            connection_pool_size=self.connection_pool_size,
            connection_timeout=self.connection_timeout,
            echo=self.echo,
        )

    @classmethod
    def from_env(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "CloudTelemetryBackendSettings":
        """从环境变量加载配置。"""

        env = environ or os.environ
        defaults = cls()
        return cls(
            app_name=env.get("CLOUD_TELEMETRY_APP_NAME", defaults.app_name),
            ingest_prefix=env.get("CLOUD_TELEMETRY_INGEST_PREFIX", defaults.ingest_prefix),
            host=env.get("CLOUD_TELEMETRY_HOST", defaults.host),
            port=_parse_int(env.get("CLOUD_TELEMETRY_PORT"), default=defaults.port),
            admin_api_keys=_parse_csv(env.get("CLOUD_TELEMETRY_ADMIN_API_KEYS")),
            default_heartbeat_interval_seconds=_parse_int(
                env.get("CLOUD_TELEMETRY_DEFAULT_HEARTBEAT_INTERVAL_SECONDS"),
                default=defaults.default_heartbeat_interval_seconds,
            ),
            challenge_ttl_seconds=_parse_int(
                env.get("CLOUD_TELEMETRY_CHALLENGE_TTL_SECONDS"),
                default=defaults.challenge_ttl_seconds,
            ),
            install_credential_ttl_seconds=_parse_int(
                env.get("CLOUD_TELEMETRY_INSTALL_CREDENTIAL_TTL_SECONDS"),
                default=defaults.install_credential_ttl_seconds,
            ),
            max_request_body_bytes=_parse_int(
                env.get("CLOUD_TELEMETRY_MAX_REQUEST_BODY_BYTES"),
                default=defaults.max_request_body_bytes,
            ),
            rate_limit_window_seconds=_parse_int(
                env.get("CLOUD_TELEMETRY_RATE_LIMIT_WINDOW_SECONDS"),
                default=defaults.rate_limit_window_seconds,
            ),
            ip_rate_limit_per_window=_parse_int(
                env.get("CLOUD_TELEMETRY_IP_RATE_LIMIT_PER_WINDOW"),
                default=defaults.ip_rate_limit_per_window,
            ),
            credential_rate_limit_per_window=_parse_int(
                env.get("CLOUD_TELEMETRY_CREDENTIAL_RATE_LIMIT_PER_WINDOW"),
                default=defaults.credential_rate_limit_per_window,
            ),
            registration_failure_limit=_parse_int(
                env.get("CLOUD_TELEMETRY_REGISTRATION_FAILURE_LIMIT"),
                default=defaults.registration_failure_limit,
            ),
            registration_failure_cooldown_seconds=_parse_int(
                env.get("CLOUD_TELEMETRY_REGISTRATION_FAILURE_COOLDOWN_SECONDS"),
                default=defaults.registration_failure_cooldown_seconds,
            ),
            offline_grace_factor=_parse_float(
                env.get("CLOUD_TELEMETRY_OFFLINE_GRACE_FACTOR"),
                default=defaults.offline_grace_factor,
            ),
            offline_scan_interval_seconds=_parse_float(
                env.get("CLOUD_TELEMETRY_OFFLINE_SCAN_INTERVAL_SECONDS"),
                default=defaults.offline_scan_interval_seconds,
            ),
            gap_recovery_window=_parse_int(
                env.get("CLOUD_TELEMETRY_GAP_RECOVERY_WINDOW"),
                default=defaults.gap_recovery_window,
            ),
            instance_detail_max_windows=_parse_int(
                env.get("CLOUD_TELEMETRY_INSTANCE_DETAIL_MAX_WINDOWS"),
                default=defaults.instance_detail_max_windows,
            ),
            instance_detail_max_diagnostic_events=_parse_int(
                env.get("CLOUD_TELEMETRY_INSTANCE_DETAIL_MAX_DIAGNOSTIC_EVENTS"),
                default=defaults.instance_detail_max_diagnostic_events,
            ),
            geoip_database_path=env.get(
                "CLOUD_TELEMETRY_GEOIP_DATABASE_PATH",
                defaults.geoip_database_path,
            ),
            database_type=env.get("CLOUD_TELEMETRY_DATABASE_TYPE", defaults.database_type),
            sqlite_path=env.get("CLOUD_TELEMETRY_SQLITE_PATH", defaults.sqlite_path),
            postgresql_host=env.get(
                "CLOUD_TELEMETRY_POSTGRESQL_HOST",
                defaults.postgresql_host,
            ),
            postgresql_port=_parse_int(
                env.get("CLOUD_TELEMETRY_POSTGRESQL_PORT"),
                default=defaults.postgresql_port,
            ),
            postgresql_database=env.get(
                "CLOUD_TELEMETRY_POSTGRESQL_DATABASE",
                defaults.postgresql_database,
            ),
            postgresql_user=env.get(
                "CLOUD_TELEMETRY_POSTGRESQL_USER",
                defaults.postgresql_user,
            ),
            postgresql_password=env.get(
                "CLOUD_TELEMETRY_POSTGRESQL_PASSWORD",
                defaults.postgresql_password,
            ),
            postgresql_schema=env.get(
                "CLOUD_TELEMETRY_POSTGRESQL_SCHEMA",
                defaults.postgresql_schema,
            ),
            postgresql_ssl_mode=env.get(
                "CLOUD_TELEMETRY_POSTGRESQL_SSL_MODE",
                defaults.postgresql_ssl_mode,
            ),
            postgresql_ssl_ca=env.get(
                "CLOUD_TELEMETRY_POSTGRESQL_SSL_CA",
                defaults.postgresql_ssl_ca,
            ),
            postgresql_ssl_cert=env.get(
                "CLOUD_TELEMETRY_POSTGRESQL_SSL_CERT",
                defaults.postgresql_ssl_cert,
            ),
            postgresql_ssl_key=env.get(
                "CLOUD_TELEMETRY_POSTGRESQL_SSL_KEY",
                defaults.postgresql_ssl_key,
            ),
            connection_pool_size=_parse_int(
                env.get("CLOUD_TELEMETRY_CONNECTION_POOL_SIZE"),
                default=defaults.connection_pool_size,
            ),
            connection_timeout=_parse_int(
                env.get("CLOUD_TELEMETRY_CONNECTION_TIMEOUT"),
                default=defaults.connection_timeout,
            ),
            echo=_parse_bool(
                env.get("CLOUD_TELEMETRY_SQL_ECHO"),
                default=defaults.echo,
            ),
        )
