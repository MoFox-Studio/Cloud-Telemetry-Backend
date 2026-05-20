"""云端遥测独立后端命令行入口。"""

from __future__ import annotations

from .app import create_cloud_telemetry_app_from_env
from .settings import CloudTelemetryBackendSettings


def main() -> None:
    """启动独立云端遥测后端。"""

    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError(
            "uvicorn is required to run cloud_telemetry_backend as a standalone server"
        ) from exc

    settings = CloudTelemetryBackendSettings.from_env()
    uvicorn.run(
        create_cloud_telemetry_app_from_env(),
        host=settings.host,
        port=settings.port,
    )


if __name__ == "__main__":
    main()