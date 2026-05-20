"""云端遥测后台只读接口测试。"""

from __future__ import annotations

import time
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from cloud_telemetry_backend.database import get_cloud_telemetry_database
from cloud_telemetry_backend.models import (
    CloudTelemetryAdminQueryAudit,
    CloudTelemetryInstance,
)

PREFIX = "/_cloud_telemetry/api"
ADMIN_HEADERS = {"X-API-Key": "test-admin-key"}


async def _ensure_registered_instance(client: httpx.AsyncClient) -> tuple[str, str]:
    """工具：注册一个安装实例并发送一次批量心跳。"""

    client_instance_id = uuid4().hex
    challenge_resp = await client.post(
        f"{PREFIX}/register/challenge",
        json={
            "client_instance_id": client_instance_id,
            "app_version": "neo-mofox-test",
            "platform": "pytest",
        },
    )
    challenge = challenge_resp.json()
    register_resp = await client.post(
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
    install_credential = register_resp.json()["install_credential"]
    await client.post(
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
                    "payload_bytes": 16,
                    "summary": {
                        "telemetry_summary": {"total_events": 2},
                        "runtime_health": {
                            "watchdog": {
                                "running": True,
                                "thread_alive": True,
                                "registered_streams": 2,
                            },
                            "stream_loop_manager": {
                                "active_streams": 1,
                                "total_failures": 3,
                            },
                        },
                        "telemetry_domains": [
                            {
                                "domain": "db",
                                "total_events": 3,
                                "error_events": 1,
                                "warning_events": 2,
                                "last_event_at": time.time(),
                            }
                        ],
                        "llm_request_name_top": [
                            {
                                "request_name": "chat.reply",
                                "request_count": 3,
                                "total_tokens": 1200,
                                "average_request_interval_seconds": 2.5,
                                "average_prompt_tokens_per_request": 200.0,
                                "average_completion_tokens_per_request": 200.0,
                                "average_latency": 1.2,
                                "cache_hit_rate": 0.5,
                                "model_identifier": "openai:gpt-test",
                                "base_urls": ["https://api.example.com/v1"],
                                "success_rate": 1.0,
                            }
                        ],
                    },
                    "diagnostic_events": [],
                }
            ],
        },
    )
    return client_instance_id, install_credential


@pytest.mark.asyncio
async def test_admin_status_requires_api_key(telemetry_client: httpx.AsyncClient) -> None:
    """缺少或错误的 X-API-Key 应被拒绝。"""

    response = await telemetry_client.get(f"{PREFIX}/admin/status")
    assert response.status_code == 403

    response = await telemetry_client.get(
        f"{PREFIX}/admin/status", headers={"X-API-Key": "wrong"}
    )
    assert response.status_code == 403

    response = await telemetry_client.get(
        f"{PREFIX}/admin/status", headers=ADMIN_HEADERS
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "cloud_telemetry"
    assert any(
        "/admin/instances" in route for route in payload["protected_admin_routes"]
    )


@pytest.mark.asyncio
async def test_admin_instances_pagination_and_masking(
    telemetry_client: httpx.AsyncClient,
) -> None:
    """整体预览列表应分页、过滤并脱敏 client_instance_id。"""

    cid, _ = await _ensure_registered_instance(telemetry_client)
    response = await telemetry_client.get(
        f"{PREFIX}/admin/instances",
        params={"limit": 5, "offset": 0},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total_count"] >= 1
    assert payload["limit"] == 5
    assert payload["offset"] == 0
    masked_ids = [item["client_instance_id_masked"] for item in payload["items"]]
    assert all("***" in masked or masked == "*" * len(masked) for masked in masked_ids)
    # 列表接口不应直接暴露原始 client_instance_id
    assert all("client_instance_id" not in item for item in payload["items"])
    item = next(
        row for row in payload["items"] if row["client_instance_id_masked"] == masked_ids[0]
    )
    detail_response = await telemetry_client.get(
        f"{PREFIX}/admin/instances/{item['client_instance_id_masked']}",
        headers=ADMIN_HEADERS,
    )
    assert detail_response.status_code == 200, detail_response.text
    assert detail_response.json()["client_instance_id_masked"] == item[
        "client_instance_id_masked"
    ]


@pytest.mark.asyncio
async def test_admin_instances_filter_by_prefix(
    telemetry_client: httpx.AsyncClient,
) -> None:
    """前缀检索 client_instance_id_prefix 应缩小返回集。"""

    cid, _ = await _ensure_registered_instance(telemetry_client)
    response = await telemetry_client.get(
        f"{PREFIX}/admin/instances",
        params={"client_instance_id_prefix": cid[:6], "limit": 10},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 200
    assert response.json()["total_count"] >= 1


@pytest.mark.asyncio
async def test_admin_instances_rejects_invalid_sort(
    telemetry_client: httpx.AsyncClient,
) -> None:
    """非白名单排序字段应被拒绝。"""

    response = await telemetry_client.get(
        f"{PREFIX}/admin/instances",
        params={"sort_by": "client_instance_id", "limit": 5},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_admin_instance_detail(
    telemetry_client: httpx.AsyncClient,
) -> None:
    """单实例详情应返回快照、最近心跳明细。"""

    cid, _ = await _ensure_registered_instance(telemetry_client)
    response = await telemetry_client.get(
        f"{PREFIX}/admin/instances/{cid}",
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["client_instance_id"] == cid
    assert payload["client_instance_id_masked"]
    assert payload["online_status"] == "active"
    assert payload["registration_status"] == "registered"
    assert isinstance(payload["recent_heartbeat_windows"], list)
    assert len(payload["recent_heartbeat_windows"]) >= 1
    latest_window = payload["recent_heartbeat_windows"][0]
    assert latest_window["summary"]["telemetry_summary"]["total_events"] == 2
    assert latest_window["summary"]["runtime_health"]["watchdog"]["running"] is True
    assert (
        latest_window["summary"]["runtime_health"]["watchdog"]["registered_streams"]
        == 2
    )
    assert latest_window["summary"]["llm_request_name_top"][0]["request_name"] == (
        "chat.reply"
    )


@pytest.mark.asyncio
async def test_admin_instance_detail_not_found_returns_404(
    telemetry_client: httpx.AsyncClient,
) -> None:
    """未知 client_instance_id 应返回 404。"""

    response = await telemetry_client.get(
        f"{PREFIX}/admin/instances/{uuid4().hex}",
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_overview_summary(
    telemetry_client: httpx.AsyncClient,
) -> None:
    """整体预览摘要应返回 total/online/offline 等聚合字段。"""

    await _ensure_registered_instance(telemetry_client)
    response = await telemetry_client.get(
        f"{PREFIX}/admin/overview/summary",
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["total_instances"] >= 1
    assert payload["online_instances"] >= 1
    assert "platform_breakdown" in payload
    assert "country_breakdown" in payload
    assert "gap_status_breakdown" in payload


@pytest.mark.asyncio
async def test_public_overview_and_frontend_pages(
    telemetry_client: httpx.AsyncClient,
) -> None:
    """公开遥测总览和页面资源不需要管理员凭证。"""

    await _ensure_registered_instance(telemetry_client)
    response = await telemetry_client.get(f"{PREFIX}/public/overview")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["overview"]["total_instances"] >= 1
    assert "performance_24h" in payload
    assert "version_distribution" in payload
    performance = payload["performance_24h"]
    assert performance["db_health"]["error_events"] >= 1
    assert performance["watchdog_running_samples"] >= 1
    assert performance["top_requests"][0]["cache_hit_rate"] == 0.5
    assert performance["top_requests"][0]["base_urls"] == [
        "https://api.example.com/v1"
    ]
    assert "avg_errors_per_heartbeat" in payload["heartbeat_timeline_24h"][-1]

    page_response = await telemetry_client.get("/_cloud_telemetry/")
    assert page_response.status_code == 200
    assert "Neo-MoFox Telemetry" in page_response.text

    admin_page_response = await telemetry_client.get("/_cloud_telemetry/admin")
    assert admin_page_response.status_code == 200
    assert "Telemetry Admin" in admin_page_response.text


@pytest.mark.asyncio
async def test_admin_diagnostics_and_instance_suspension(
    telemetry_client: httpx.AsyncClient,
) -> None:
    """管理员可以查看诊断聚合，并封禁/解封指定实例。"""

    cid, _ = await _ensure_registered_instance(telemetry_client)
    diagnostics_response = await telemetry_client.get(
        f"{PREFIX}/admin/diagnostics/summary",
        headers=ADMIN_HEADERS,
    )
    assert diagnostics_response.status_code == 200, diagnostics_response.text
    diagnostics = diagnostics_response.json()
    assert "error_rate_24h" in diagnostics
    assert "performance_24h" in diagnostics
    assert diagnostics["performance_24h"]["db_health"]["error_events"] >= 1
    assert diagnostics["performance_24h"]["stream_failures_max"] >= 3

    suspend_response = await telemetry_client.post(
        f"{PREFIX}/admin/instances/{cid}/suspend",
        headers=ADMIN_HEADERS,
        json={"reason": "test quarantine"},
    )
    assert suspend_response.status_code == 200, suspend_response.text
    suspended = suspend_response.json()
    assert suspended["is_suspended"] is True
    assert suspended["suspension_reason"] == "test quarantine"

    resume_response = await telemetry_client.post(
        f"{PREFIX}/admin/instances/{cid}/resume",
        headers=ADMIN_HEADERS,
        json={},
    )
    assert resume_response.status_code == 200, resume_response.text
    assert resume_response.json()["is_suspended"] is False


@pytest.mark.asyncio
async def test_admin_queries_are_audited(
    telemetry_client: httpx.AsyncClient,
) -> None:
    """后台查询应写入审计表。"""

    cid, _ = await _ensure_registered_instance(telemetry_client)
    await telemetry_client.get(
        f"{PREFIX}/admin/instances/{cid}", headers=ADMIN_HEADERS
    )
    await telemetry_client.get(
        f"{PREFIX}/admin/instances", headers=ADMIN_HEADERS, params={"limit": 5}
    )
    await telemetry_client.get(
        f"{PREFIX}/admin/overview/summary", headers=ADMIN_HEADERS
    )

    database = get_cloud_telemetry_database()
    async with database.session() as session:
        rows = (
            await session.execute(
                select(CloudTelemetryAdminQueryAudit).order_by(
                    CloudTelemetryAdminQueryAudit.id.asc()
                )
            )
        ).scalars().all()

    query_types = {row.query_type for row in rows}
    assert {"instance_detail", "instance_list", "overview_summary"}.issubset(query_types)
    detail_rows = [row for row in rows if row.query_type == "instance_detail"]
    assert any(row.target_client_instance_id == cid for row in detail_rows)


@pytest.mark.asyncio
async def test_suspended_instance_returns_rejected_permanent(
    telemetry_client: httpx.AsyncClient,
) -> None:
    """实例级停传：所有窗口直接 rejected_permanent 且响应 instance_status=suspended。"""

    cid, install_credential = await _ensure_registered_instance(telemetry_client)

    # 直接通过 ORM 把实例标记为 suspended
    database = get_cloud_telemetry_database()
    async with database.session() as session:
        instance = (
            await session.execute(
                select(CloudTelemetryInstance).where(
                    CloudTelemetryInstance.client_instance_id == cid
                )
            )
        ).scalars().first()
        assert instance is not None
        instance.is_suspended = True
        instance.suspended_at = time.time()
        instance.suspension_reason = "manual_suspend_for_test"
        await session.commit()

    response = await telemetry_client.post(
        f"{PREFIX}/heartbeats/batch",
        json={
            "request_id": uuid4().hex,
            "client_instance_id": cid,
            "install_credential": install_credential,
            "windows": [
                {
                    "window_sequence": 99,
                    "window_started_at": time.time() - 10,
                    "window_ended_at": time.time(),
                    "payload_bytes": 0,
                    "summary": {},
                    "diagnostic_events": [],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["instance_status"] == "suspended"
    assert payload["accepted_window_count"] == 0
    assert payload["rejected_window_count"] == 1
    assert payload["window_results"][0]["status"] == "rejected_permanent"
    assert payload["window_results"][0]["reason"] == "manual_suspend_for_test"


@pytest.mark.asyncio
async def test_diagnostic_attributes_whitelist_enforced(
    telemetry_client: httpx.AsyncClient,
) -> None:
    """诊断事件中的非白名单字段应被服务端过滤掉。"""

    from cloud_telemetry_backend.models import CloudTelemetryDiagnosticEvent

    cid, install_credential = await _ensure_registered_instance(telemetry_client)
    response = await telemetry_client.post(
        f"{PREFIX}/heartbeats/batch",
        json={
            "request_id": uuid4().hex,
            "client_instance_id": cid,
            "install_credential": install_credential,
            "windows": [
                {
                    "window_sequence": 2,
                    "window_started_at": time.time() - 10,
                    "window_ended_at": time.time(),
                    "payload_bytes": 16,
                    "summary": {},
                    "diagnostic_events": [
                        {
                            "event_name": "runtime.error",
                            "severity": "error",
                            "event_at": time.time() - 5,
                            "summary": "boom",
                            "attributes": {
                                "domain": "runtime",
                                "entity_id": "stream-2",
                                "secret_key": "should_be_dropped",
                                "detail_json": "{\"big\": \"payload\"}",
                            },
                        }
                    ],
                }
            ],
        },
    )
    assert response.status_code == 200, response.text

    database = get_cloud_telemetry_database()
    async with database.session() as session:
        events = (
            await session.execute(
                select(CloudTelemetryDiagnosticEvent).where(
                    CloudTelemetryDiagnosticEvent.event_name == "runtime.error"
                )
            )
        ).scalars().all()
    assert events
    import json as _json

    for event in events:
        attributes = _json.loads(event.attributes_json)
        assert set(attributes.keys()).issubset({"domain", "entity_id"})
