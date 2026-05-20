"""离线扫描与 GeoIP 模块的单元测试。"""

from __future__ import annotations

import time
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from cloud_telemetry_backend.database import get_cloud_telemetry_database
from cloud_telemetry_backend.geoip import GeoIPResolver, GeoLookupResult
from cloud_telemetry_backend.models import (
    CloudTelemetryInstance,
    CloudTelemetryInstanceSnapshot,
)
from cloud_telemetry_backend.scanner import OfflineDeadlineScanner

PREFIX = "/_cloud_telemetry/api"


@pytest.mark.asyncio
async def test_offline_scanner_marks_expired_active_instances_as_offline(
    telemetry_client: httpx.AsyncClient,
) -> None:
    """offline_deadline_at 已过期且仍 active 的实例应被扫描器标记为 offline。"""

    # 先制造一个 active 实例
    client_instance_id = uuid4().hex
    challenge = (
        await telemetry_client.post(
            f"{PREFIX}/register/challenge",
            json={
                "client_instance_id": client_instance_id,
                "app_version": "neo-mofox-test",
                "platform": "pytest",
            },
        )
    ).json()
    install_credential = (
        await telemetry_client.post(
            f"{PREFIX}/register",
            json={
                "client_instance_id": client_instance_id,
                "challenge_id": challenge["challenge_id"],
                "challenge_token": challenge["challenge_token"],
                "allow_ip_retention": True,
                "app_version": "neo-mofox-test",
                "platform": "pytest",
            },
        )
    ).json()["install_credential"]
    await telemetry_client.post(
        f"{PREFIX}/heartbeats/batch",
        json={
            "request_id": uuid4().hex,
            "client_instance_id": client_instance_id,
            "install_credential": install_credential,
            "windows": [
                {
                    "window_sequence": 1,
                    "window_started_at": time.time() - 10,
                    "window_ended_at": time.time(),
                    "payload_bytes": 8,
                    "summary": {},
                    "diagnostic_events": [],
                }
            ],
        },
    )

    database = get_cloud_telemetry_database()
    async with database.session() as session:
        instance = (
            await session.execute(
                select(CloudTelemetryInstance).where(
                    CloudTelemetryInstance.client_instance_id == client_instance_id
                )
            )
        ).scalars().first()
        assert instance is not None
        snapshot = (
            await session.execute(
                select(CloudTelemetryInstanceSnapshot).where(
                    CloudTelemetryInstanceSnapshot.instance_id == instance.id
                )
            )
        ).scalars().first()
        assert snapshot is not None
        assert snapshot.online_status == "active"

        # 把 offline_deadline_at 设为过去时间
        snapshot.offline_deadline_at = time.time() - 100
        await session.commit()

    scanner = OfflineDeadlineScanner(scan_interval_seconds=1.0)
    changed = await scanner.run_once()
    assert changed >= 1

    async with database.session() as session:
        snapshot = (
            await session.execute(
                select(CloudTelemetryInstanceSnapshot).where(
                    CloudTelemetryInstanceSnapshot.instance_id == instance.id
                )
            )
        ).scalars().first()
        assert snapshot is not None
        assert snapshot.online_status == "offline"


def test_geoip_resolver_returns_empty_when_disabled() -> None:
    """未配置 GeoIP 数据库时 lookup 应返回空结果。"""

    resolver = GeoIPResolver(database_path=None)
    assert resolver.enabled is False
    result = resolver.lookup("8.8.8.8")
    assert result == GeoLookupResult(country_code=None, region_code=None)


def test_geoip_resolver_returns_empty_for_private_ip() -> None:
    """私有/回环/本地 IP 应直接返回空，不触发数据库查询。"""

    resolver = GeoIPResolver(database_path=None)
    assert resolver.lookup("127.0.0.1") == GeoLookupResult(None, None)
    assert resolver.lookup("10.0.0.1") == GeoLookupResult(None, None)
    assert resolver.lookup("192.168.1.1") == GeoLookupResult(None, None)
    assert resolver.lookup("::1") == GeoLookupResult(None, None)


def test_geoip_resolver_handles_invalid_ip_gracefully() -> None:
    """非法 IP 字符串不应抛异常，返回空结果。"""

    resolver = GeoIPResolver(database_path=None)
    assert resolver.lookup("not-an-ip") == GeoLookupResult(None, None)
    assert resolver.lookup("") == GeoLookupResult(None, None)
    assert resolver.lookup(None) == GeoLookupResult(None, None)
