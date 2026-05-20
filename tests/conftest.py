"""云端遥测独立后端测试公共 fixture。"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from fastapi import FastAPI

# 让 `import cloud_telemetry_backend` 在测试中可用
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from cloud_telemetry_backend.app import create_cloud_telemetry_app
from cloud_telemetry_backend.settings import CloudTelemetryBackendSettings


@pytest.fixture
def event_loop():
    """为每个测试用例创建独立事件循环。"""

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def telemetry_settings(tmp_path: Path) -> CloudTelemetryBackendSettings:
    """构建一份基于 SQLite 的独立后端配置。"""

    return CloudTelemetryBackendSettings(
        ingest_prefix="/_cloud_telemetry",
        admin_api_keys=("test-admin-key",),
        default_heartbeat_interval_seconds=10,
        challenge_ttl_seconds=60,
        offline_grace_factor=2.0,
        offline_scan_interval_seconds=0.5,
        gap_recovery_window=5,
        instance_detail_max_windows=20,
        instance_detail_max_diagnostic_events=20,
        database_type="sqlite",
        sqlite_path=str(tmp_path / "cloud_telemetry.db"),
    )


@pytest_asyncio.fixture
async def telemetry_client(
    telemetry_settings: CloudTelemetryBackendSettings,
) -> AsyncIterator[httpx.AsyncClient]:
    """构建一个绑定 ASGI 应用并显式驱动 lifespan 的 AsyncClient。"""

    app: FastAPI = create_cloud_telemetry_app(telemetry_settings)
    async with LifespanManager(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            yield client
