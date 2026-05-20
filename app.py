"""云端遥测独立后端 ASGI 应用工厂。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from .database import close_cloud_telemetry_database, init_cloud_telemetry_database
from .geoip import close_geoip_resolver, init_geoip_resolver
from .ingress import CloudTelemetryIngress
from .scanner import close_offline_scanner, init_offline_scanner
from .settings import CloudTelemetryBackendSettings


def build_admin_api_key_dependency(
    settings: CloudTelemetryBackendSettings,
) -> Callable[..., Any]:
    """构建独立后端使用的管理接口鉴权依赖。"""

    async def verify_admin_api_key(
        x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> None:
        if not settings.admin_api_keys:
            return
        if x_api_key in settings.admin_api_keys:
            return
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="invalid api key",
        )

    return verify_admin_api_key


def create_cloud_telemetry_app(
    settings: CloudTelemetryBackendSettings | None = None,
) -> FastAPI:
    """创建独立云端遥测 FastAPI 应用。"""

    effective_settings = settings or CloudTelemetryBackendSettings.from_env()
    verify_admin_api_key = build_admin_api_key_dependency(effective_settings)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        await init_cloud_telemetry_database(effective_settings.to_storage_config())
        init_geoip_resolver(effective_settings.geoip_database_path)
        scanner = init_offline_scanner(
            scan_interval_seconds=effective_settings.offline_scan_interval_seconds,
        )
        await scanner.start()
        try:
            yield
        finally:
            await close_offline_scanner()
            close_geoip_resolver()
            await close_cloud_telemetry_database()

    app = FastAPI(
        title=effective_settings.app_name,
        lifespan=lifespan,
    )
    app.state.cloud_telemetry_settings = effective_settings

    @app.middleware("http")
    async def enforce_request_body_limit(request: Request, call_next: Callable[..., Any]):
        max_bytes = max(1, int(effective_settings.max_request_body_bytes))
        content_length = request.headers.get("content-length")
        if content_length is not None:
            try:
                declared_length = int(content_length or "0")
            except ValueError:
                declared_length = max_bytes + 1
            if declared_length > max_bytes:
                return JSONResponse(
                    {"error": "request body too large"},
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                )
        body = await request.body()
        if len(body) > max_bytes:
            return JSONResponse(
                {"error": "request body too large"},
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        return await call_next(request)

    ingress = CloudTelemetryIngress(
        settings=effective_settings,
        admin_dependencies=[Depends(verify_admin_api_key)],
    )
    ingress.mount(app, prefix=effective_settings.ingest_prefix)
    return app


def create_cloud_telemetry_app_from_env() -> FastAPI:
    """从环境变量创建独立云端遥测应用。"""

    return create_cloud_telemetry_app(CloudTelemetryBackendSettings.from_env())


app = create_cloud_telemetry_app_from_env()
