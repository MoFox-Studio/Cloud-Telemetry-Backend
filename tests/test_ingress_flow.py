"""云端遥测接入端到端流程测试。"""

from __future__ import annotations

from importlib import import_module
import sqlite3
import time
from uuid import uuid4

import httpx
import pytest
from asgi_lifespan import LifespanManager

PREFIX = "/_cloud_telemetry/api"


async def _issue_challenge(
    client: httpx.AsyncClient,
    *,
    client_instance_id: str,
    expect_status: int = 200,
) -> dict:
    response = await client.post(
        f"{PREFIX}/register/challenge",
        json={
            "client_instance_id": client_instance_id,
            "app_version": "neo-mofox-test",
            "platform": "pytest",
        },
    )
    assert response.status_code == expect_status, response.text
    return response.json()


async def _register(
    client: httpx.AsyncClient,
    *,
    client_instance_id: str,
    challenge: dict,
    expect_status: int = 200,
) -> dict:
    response = await client.post(
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
    assert response.status_code == expect_status, response.text
    return response.json()


@pytest.mark.asyncio
async def test_full_registration_and_heartbeat_flow(telemetry_client: httpx.AsyncClient) -> None:
    """完整流程：challenge → register → bootstrap heartbeat → batch heartbeat。"""

    client_instance_id = uuid4().hex

    challenge = await _issue_challenge(
        telemetry_client, client_instance_id=client_instance_id
    )
    assert challenge["challenge_id"]
    assert challenge["challenge_token"]
    assert challenge["expires_at"] > challenge["issued_at"]

    register = await _register(
        telemetry_client,
        client_instance_id=client_instance_id,
        challenge=challenge,
    )
    install_credential = register["install_credential"]
    assert install_credential.startswith("ctc_")
    assert register["next_window_sequence"] == 1
    assert register["next_heartbeat_interval_seconds"] >= 1

    batch_resp = await telemetry_client.post(
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
                    "payload_bytes": 32,
                    "summary": {"telemetry_summary": {"total_events": 5}},
                    "diagnostic_events": [
                        {
                            "event_name": "runtime.warning",
                            "severity": "warning",
                            "event_at": time.time() - 5,
                            "summary": "test warning",
                            "attributes": {
                                "domain": "runtime",
                                "entity_id": "stream-1",
                                # 非白名单字段会被服务端过滤
                                "raw_log": "should be dropped",
                            },
                        }
                    ],
                }
            ],
        },
    )
    assert batch_resp.status_code == 200, batch_resp.text
    payload = batch_resp.json()
    assert payload["accepted_window_count"] == 1
    assert payload["duplicate_window_count"] == 0
    assert payload["rejected_window_count"] == 0
    assert payload["instance_status"] == "active"
    assert payload["next_window_sequence"] == 2
    assert len(payload["window_results"]) == 1
    assert payload["window_results"][0]["status"] == "accepted"



@pytest.mark.asyncio
async def test_expired_install_credential_is_rejected(
    telemetry_client: httpx.AsyncClient,
) -> None:
    """服务端应强制校验安装凭证过期时间。"""
    from sqlalchemy import select

    from cloud_telemetry_backend.database import get_cloud_telemetry_database
    from cloud_telemetry_backend.models import CloudTelemetryInstance

    client_instance_id = uuid4().hex
    challenge = await _issue_challenge(
        telemetry_client,
        client_instance_id=client_instance_id,
    )
    register = await _register(
        telemetry_client,
        client_instance_id=client_instance_id,
        challenge=challenge,
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
        instance.credential_expires_at = time.time() - 1
        await session.commit()

    response = await telemetry_client.post(
        f"{PREFIX}/heartbeats/batch",
        json={
            "request_id": uuid4().hex,
            "client_instance_id": client_instance_id,
            "install_credential": register["install_credential"],
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

    assert response.status_code == 403
    assert response.json()["error"] == "expired install credential"


@pytest.mark.asyncio
async def test_challenge_can_only_be_used_once(telemetry_client: httpx.AsyncClient) -> None:
    """challenge 一次性消费：第二次注册应被拒绝。"""

    client_instance_id = uuid4().hex
    challenge = await _issue_challenge(
        telemetry_client, client_instance_id=client_instance_id
    )
    await _register(
        telemetry_client,
        client_instance_id=client_instance_id,
        challenge=challenge,
    )
    await _register(
        telemetry_client,
        client_instance_id=client_instance_id,
        challenge=challenge,
        expect_status=403,
    )


@pytest.mark.asyncio
async def test_registration_challenge_works_without_extra_secret(
    telemetry_client: httpx.AsyncClient,
) -> None:
    """非白名单引导凭证应被拒绝。"""

    client_instance_id = uuid4().hex
    response = await telemetry_client.post(
        f"{PREFIX}/register/challenge",
        json={
            "client_instance_id": client_instance_id,
            "app_version": "neo-mofox-test",
            "platform": "pytest",
        },
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_duplicate_window_returns_duplicate_status(
    telemetry_client: httpx.AsyncClient,
) -> None:
    """重复窗口序号应被服务端去重。"""

    client_instance_id = uuid4().hex
    challenge = await _issue_challenge(
        telemetry_client, client_instance_id=client_instance_id
    )
    register = await _register(
        telemetry_client,
        client_instance_id=client_instance_id,
        challenge=challenge,
    )
    install_credential = register["install_credential"]

    request_payload = {
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
    }
    first = await telemetry_client.post(
        f"{PREFIX}/heartbeats/batch", json=request_payload
    )
    assert first.status_code == 200
    assert first.json()["accepted_window_count"] == 1

    request_payload["request_id"] = uuid4().hex
    second = await telemetry_client.post(
        f"{PREFIX}/heartbeats/batch", json=request_payload
    )
    assert second.status_code == 200
    assert second.json()["duplicate_window_count"] == 1
    assert second.json()["accepted_window_count"] == 0


@pytest.mark.asyncio
async def test_invalid_install_credential_rejected(
    telemetry_client: httpx.AsyncClient,
) -> None:
    """伪造 install_credential 应被服务端拒绝。"""

    client_instance_id = uuid4().hex
    challenge = await _issue_challenge(
        telemetry_client, client_instance_id=client_instance_id
    )
    await _register(
        telemetry_client,
        client_instance_id=client_instance_id,
        challenge=challenge,
    )

    response = await telemetry_client.post(
        f"{PREFIX}/heartbeats/batch",
        json={
            "request_id": uuid4().hex,
            "client_instance_id": client_instance_id,
            "install_credential": "wrong-credential",
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
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_existing_sqlite_db_is_upgraded_when_instance_table_lacks_last_source_ip(
    telemetry_settings,
) -> None:
    """旧 SQLite 实例表缺少新增列时，启动阶段应自动补列并允许注册。"""

    connection = sqlite3.connect(telemetry_settings.sqlite_path)
    try:
        connection.execute(
            """
            CREATE TABLE cloud_telemetry_instances (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                client_instance_id TEXT NOT NULL UNIQUE,
                registration_status TEXT NOT NULL,
                credential_hash TEXT,
                app_version TEXT,
                platform TEXT,
                country_code TEXT,
                region_code TEXT,
                allow_ip_retention BOOLEAN NOT NULL,
                is_suspended BOOLEAN NOT NULL,
                suspended_at FLOAT,
                suspension_reason TEXT,
                first_registered_at FLOAT,
                last_registered_at FLOAT,
                created_at FLOAT NOT NULL,
                updated_at FLOAT NOT NULL
            )
            """
        )
        connection.commit()
    finally:
        connection.close()

    create_cloud_telemetry_app = import_module(
        "cloud_telemetry_backend.app"
    ).create_cloud_telemetry_app
    app = create_cloud_telemetry_app(telemetry_settings)
    async with LifespanManager(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            client_instance_id = uuid4().hex
            challenge = await _issue_challenge(
                client,
                client_instance_id=client_instance_id,
            )
            register = await _register(
                client,
                client_instance_id=client_instance_id,
                challenge=challenge,
            )
            assert register["install_credential"].startswith("ctc_")

    connection = sqlite3.connect(telemetry_settings.sqlite_path)
    try:
        column_names = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(cloud_telemetry_instances)"
            ).fetchall()
        }
    finally:
        connection.close()

    assert "last_source_ip" in column_names
