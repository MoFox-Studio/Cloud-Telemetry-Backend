"""云端遥测后台只读管理服务。

按 CONTEXT.md 首版后台范围：
- 按 client_instance_id 检索单实例详情。
- 整体预览分页列表（offset/limit + 服务端过滤 + 白名单排序）。
- 整体预览摘要（基于安装实例主表与实例状态快照层实时聚合）。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from sqlalchemy import and_, func, select

from .database import get_cloud_telemetry_database
from .identifier_mask import mask_client_instance_id
from .models import (
    CloudTelemetryDiagnosticEvent,
    CloudTelemetryHeartbeatWindow,
    CloudTelemetryInstance,
    CloudTelemetryInstanceSnapshot,
)
from .protocol import (
    CloudTelemetryAdminDiagnosticEventDetail,
    CloudTelemetryAdminHeartbeatWindowDetail,
    CloudTelemetryAdminInstanceDetailResponse,
    CloudTelemetryAdminInstanceListResponse,
    CloudTelemetryAdminInstanceSummary,
    CloudTelemetryAdminOverviewSummaryResponse,
)
from .settings import CloudTelemetryBackendSettings

logger = logging.getLogger("cloud_telemetry_backend.admin")


# 列表接口允许的排序字段白名单
_LIST_SORT_FIELDS: dict[str, Any] = {
    "last_heartbeat_received_at": CloudTelemetryInstanceSnapshot.last_heartbeat_received_at,
    "last_success_heartbeat_at": CloudTelemetryInstanceSnapshot.last_success_heartbeat_at,
    "first_registered_at": CloudTelemetryInstance.first_registered_at,
    "last_registered_at": CloudTelemetryInstance.last_registered_at,
    "online_status": CloudTelemetryInstanceSnapshot.online_status,
}

_LIST_SORT_ORDERS = frozenset({"asc", "desc"})

_ALLOWED_ONLINE_STATUSES = frozenset({"active", "offline", "suspended"})

_MAX_LIST_LIMIT = 200


class CloudTelemetryAdminService:
    """后台只读管理服务。"""

    def __init__(self, settings: CloudTelemetryBackendSettings) -> None:
        self._settings = settings

    async def get_overview_summary(self) -> CloudTelemetryAdminOverviewSummaryResponse:
        """整体预览摘要：实时聚合安装实例主表与状态快照。"""

        database = self._require_database()
        async with database.session() as session:
            total_instances = int(
                (
                    await session.execute(
                        select(func.count()).select_from(CloudTelemetryInstance)
                    )
                ).scalar_one()
            )

            online_status_rows = (
                await session.execute(
                    select(
                        CloudTelemetryInstanceSnapshot.online_status,
                        func.count().label("cnt"),
                    ).group_by(CloudTelemetryInstanceSnapshot.online_status)
                )
            ).all()
            online_status_breakdown: dict[str, int] = {
                str(row.online_status): int(row.cnt) for row in online_status_rows
            }

            gap_rows = (
                await session.execute(
                    select(
                        CloudTelemetryInstanceSnapshot.gap_status,
                        func.count().label("cnt"),
                    ).group_by(CloudTelemetryInstanceSnapshot.gap_status)
                )
            ).all()
            gap_status_breakdown: dict[str, int] = {
                str(row.gap_status): int(row.cnt) for row in gap_rows
            }

            platform_rows = (
                await session.execute(
                    select(
                        CloudTelemetryInstance.platform,
                        func.count().label("cnt"),
                    ).group_by(CloudTelemetryInstance.platform)
                )
            ).all()
            platform_breakdown: dict[str, int] = {
                _coerce_label(row.platform): int(row.cnt) for row in platform_rows
            }

            country_rows = (
                await session.execute(
                    select(
                        CloudTelemetryInstance.country_code,
                        func.count().label("cnt"),
                    ).group_by(CloudTelemetryInstance.country_code)
                )
            ).all()
            country_breakdown: dict[str, int] = {
                _coerce_label(row.country_code): int(row.cnt) for row in country_rows
            }

            suspended_count = int(
                (
                    await session.execute(
                        select(func.count())
                        .select_from(CloudTelemetryInstance)
                        .where(CloudTelemetryInstance.is_suspended.is_(True))
                    )
                ).scalar_one()
            )

        online_count = online_status_breakdown.get("active", 0)
        offline_count = online_status_breakdown.get("offline", 0)
        return CloudTelemetryAdminOverviewSummaryResponse(
            total_instances=total_instances,
            online_instances=online_count,
            offline_instances=offline_count,
            suspended_instances=suspended_count,
            gap_status_breakdown=gap_status_breakdown,
            platform_breakdown=platform_breakdown,
            country_breakdown=country_breakdown,
            server_time=time.time(),
        )

    async def get_public_overview(self) -> dict[str, Any]:
        """Public community-facing telemetry overview."""

        database = self._require_database()
        now = time.time()
        day_ago = now - 86400
        two_weeks_ago = now - 14 * 86400
        async with database.session() as session:
            overview = await self.get_overview_summary()
            version_rows = (
                await session.execute(
                    select(
                        CloudTelemetryInstance.app_version,
                        func.count().label("cnt"),
                    ).group_by(CloudTelemetryInstance.app_version)
                )
            ).all()
            registration_rows = (
                await session.execute(
                    select(
                        CloudTelemetryInstance.app_version,
                        CloudTelemetryInstance.first_registered_at,
                    ).where(CloudTelemetryInstance.first_registered_at >= two_weeks_ago)
                )
            ).all()
            recent_windows = (
                await session.execute(
                    select(CloudTelemetryHeartbeatWindow)
                    .where(CloudTelemetryHeartbeatWindow.received_at >= day_ago)
                    .order_by(CloudTelemetryHeartbeatWindow.received_at.desc())
                )
            ).scalars().all()
            diagnostic_rows = (
                await session.execute(
                    select(
                        CloudTelemetryDiagnosticEvent.severity,
                        func.count().label("cnt"),
                    )
                    .where(CloudTelemetryDiagnosticEvent.received_at >= day_ago)
                    .group_by(CloudTelemetryDiagnosticEvent.severity)
                )
            ).all()
            diagnostics = (
                await session.execute(
                    select(CloudTelemetryDiagnosticEvent)
                    .where(CloudTelemetryDiagnosticEvent.received_at >= day_ago)
                    .order_by(CloudTelemetryDiagnosticEvent.received_at.desc())
                    .limit(1200)
                )
            ).scalars().all()

        return {
            "server_time": now,
            "overview": overview.model_dump(mode="json"),
            "version_distribution": [
                {"version": _coerce_label(row.app_version), "count": int(row.cnt)}
                for row in version_rows
            ],
            "version_adoption_trend": _build_version_adoption_trend(
                registration_rows,
                now=now,
                days=14,
            ),
            "diagnostic_breakdown_24h": {
                _coerce_label(row.severity): int(row.cnt) for row in diagnostic_rows
            },
            "performance_24h": _summarize_window_performance(
                recent_windows,
                include_base_urls=False,
            ),
            "heartbeat_timeline_24h": _build_window_timeline(
                recent_windows,
                diagnostics=diagnostics,
                now=now,
            ),
        }

    async def get_admin_diagnostics_summary(self) -> dict[str, Any]:
        """Admin troubleshooting aggregates for recent stability signals."""

        database = self._require_database()
        now = time.time()
        day_ago = now - 86400
        async with database.session() as session:
            recent_windows = (
                await session.execute(
                    select(CloudTelemetryHeartbeatWindow)
                    .where(CloudTelemetryHeartbeatWindow.received_at >= day_ago)
                    .order_by(CloudTelemetryHeartbeatWindow.received_at.desc())
                    .limit(1500)
                )
            ).scalars().all()
            diagnostics = (
                await session.execute(
                    select(CloudTelemetryDiagnosticEvent)
                    .where(CloudTelemetryDiagnosticEvent.received_at >= day_ago)
                    .order_by(CloudTelemetryDiagnosticEvent.received_at.desc())
                )
            ).scalars().all()

        error_like = [
            item
            for item in diagnostics
            if str(item.severity).lower() in {"error", "critical", "fatal"}
        ]
        return {
            "server_time": now,
            "window_count_24h": len(recent_windows),
            "diagnostic_count_24h": len(diagnostics),
            "error_count_24h": len(error_like),
            "error_rate_24h": (
                len(error_like) / len(recent_windows) if recent_windows else 0.0
            ),
            "performance_24h": _summarize_window_performance(recent_windows),
            "diagnostic_timeline_24h": _build_diagnostic_timeline(diagnostics, now=now),
            "recent_error_events": [
                {
                    "window_sequence": event.window_sequence,
                    "event_at": event.event_at,
                    "received_at": event.received_at,
                    "severity": event.severity,
                    "event_name": event.event_name,
                    "summary": event.summary,
                }
                for event in error_like[:80]
            ],
        }

    async def set_instance_suspension(
        self,
        client_instance_id: str,
        *,
        suspended: bool,
        reason: str | None = None,
    ) -> CloudTelemetryAdminInstanceDetailResponse:
        """Suspend or resume one client instance."""

        database = self._require_database()
        now = time.time()
        async with database.session() as session:
            instance = await _find_instance_by_admin_identifier(
                session,
                client_instance_id,
            )
            if instance is None:
                raise LookupError(
                    f"client_instance_id not found: {client_instance_id}"
                )

            instance.is_suspended = suspended
            instance.suspended_at = now if suspended else None
            instance.suspension_reason = reason if suspended else None
            instance.updated_at = now

            snapshot = (
                await session.execute(
                    select(CloudTelemetryInstanceSnapshot).where(
                        CloudTelemetryInstanceSnapshot.instance_id == instance.id
                    )
                )
            ).scalars().first()
            if snapshot is not None:
                snapshot.online_status = "suspended" if suspended else "offline"
                snapshot.online_status_updated_at = now
                snapshot.last_heartbeat_result = (
                    "admin_suspended" if suspended else "admin_resumed"
                )
                snapshot.updated_at = now
            await session.commit()

        return await self.get_instance_detail(client_instance_id)

    async def list_instances(
        self,
        *,
        offset: int = 0,
        limit: int = 20,
        online_status: str | None = None,
        platform: str | None = None,
        app_version: str | None = None,
        country_code: str | None = None,
        is_suspended: bool | None = None,
        client_instance_id_prefix: str | None = None,
        sort_by: str = "last_heartbeat_received_at",
        sort_order: str = "desc",
    ) -> CloudTelemetryAdminInstanceListResponse:
        """整体预览分页列表。"""

        if offset < 0:
            raise ValueError("offset must be non-negative")
        if limit < 1 or limit > _MAX_LIST_LIMIT:
            raise ValueError(f"limit must be in [1, {_MAX_LIST_LIMIT}]")
        if sort_by not in _LIST_SORT_FIELDS:
            raise ValueError(
                f"sort_by must be one of: {', '.join(sorted(_LIST_SORT_FIELDS.keys()))}"
            )
        if sort_order not in _LIST_SORT_ORDERS:
            raise ValueError("sort_order must be 'asc' or 'desc'")
        if online_status is not None and online_status not in _ALLOWED_ONLINE_STATUSES:
            raise ValueError(
                f"online_status must be one of: {', '.join(sorted(_ALLOWED_ONLINE_STATUSES))}"
            )

        database = self._require_database()
        sort_column = _LIST_SORT_FIELDS[sort_by]
        sort_clause = sort_column.desc() if sort_order == "desc" else sort_column.asc()

        async with database.session() as session:
            base_filters = []
            if online_status is not None:
                base_filters.append(
                    CloudTelemetryInstanceSnapshot.online_status == online_status
                )
            if platform is not None:
                base_filters.append(CloudTelemetryInstance.platform == platform)
            if app_version is not None:
                base_filters.append(CloudTelemetryInstance.app_version == app_version)
            if country_code is not None:
                base_filters.append(
                    CloudTelemetryInstance.country_code == country_code
                )
            if is_suspended is not None:
                base_filters.append(CloudTelemetryInstance.is_suspended.is_(is_suspended))
            if client_instance_id_prefix:
                base_filters.append(
                    CloudTelemetryInstance.client_instance_id.like(
                        f"{client_instance_id_prefix}%"
                    )
                )

            count_stmt = (
                select(func.count())
                .select_from(CloudTelemetryInstance)
                .join(
                    CloudTelemetryInstanceSnapshot,
                    CloudTelemetryInstanceSnapshot.instance_id
                    == CloudTelemetryInstance.id,
                    isouter=True,
                )
            )
            if base_filters:
                count_stmt = count_stmt.where(and_(*base_filters))
            total_count = int((await session.execute(count_stmt)).scalar_one())

            list_stmt = (
                select(
                    CloudTelemetryInstance,
                    CloudTelemetryInstanceSnapshot,
                )
                .join(
                    CloudTelemetryInstanceSnapshot,
                    CloudTelemetryInstanceSnapshot.instance_id
                    == CloudTelemetryInstance.id,
                    isouter=True,
                )
            )
            if base_filters:
                list_stmt = list_stmt.where(and_(*base_filters))
            list_stmt = list_stmt.order_by(sort_clause).offset(offset).limit(limit)

            rows = (await session.execute(list_stmt)).all()

        items: list[CloudTelemetryAdminInstanceSummary] = []
        for row in rows:
            instance: CloudTelemetryInstance = row[0]
            snapshot: CloudTelemetryInstanceSnapshot | None = row[1]
            items.append(
                CloudTelemetryAdminInstanceSummary(
                    client_instance_id_masked=mask_client_instance_id(
                        instance.client_instance_id
                    ),
                    online_status=(
                        snapshot.online_status if snapshot is not None else "offline"
                    ),
                    last_heartbeat_received_at=(
                        snapshot.last_heartbeat_received_at if snapshot is not None else None
                    ),
                    last_success_heartbeat_at=(
                        snapshot.last_success_heartbeat_at if snapshot is not None else None
                    ),
                    last_window_sequence=(
                        snapshot.last_window_sequence if snapshot is not None else None
                    ),
                    gap_status=(
                        snapshot.gap_status if snapshot is not None else "healthy"
                    ),
                    is_suspended=instance.is_suspended,
                    app_version=instance.app_version,
                    platform=instance.platform,
                    country_code=instance.country_code,
                    region_code=instance.region_code,
                    last_diagnostic_severity=(
                        snapshot.last_diagnostic_severity if snapshot is not None else None
                    ),
                    last_diagnostic_at=(
                        snapshot.last_diagnostic_at if snapshot is not None else None
                    ),
                    first_registered_at=instance.first_registered_at,
                )
            )

        return CloudTelemetryAdminInstanceListResponse(
            total_count=total_count,
            items=items,
            offset=offset,
            limit=limit,
        )

    async def get_instance_detail(
        self, client_instance_id: str
    ) -> CloudTelemetryAdminInstanceDetailResponse:
        """单实例详情。"""

        database = self._require_database()
        max_windows = max(1, int(self._settings.instance_detail_max_windows))
        max_diagnostics = max(
            1, int(self._settings.instance_detail_max_diagnostic_events)
        )

        async with database.session() as session:
            instance = await _find_instance_by_admin_identifier(
                session,
                client_instance_id,
            )

            if instance is None:
                raise LookupError(
                    f"client_instance_id not found: {client_instance_id}"
                )

            snapshot = (
                await session.execute(
                    select(CloudTelemetryInstanceSnapshot).where(
                        CloudTelemetryInstanceSnapshot.instance_id == instance.id
                    )
                )
            ).scalars().first()

            recent_windows_rows = (
                await session.execute(
                    select(CloudTelemetryHeartbeatWindow)
                    .where(CloudTelemetryHeartbeatWindow.instance_id == instance.id)
                    .order_by(CloudTelemetryHeartbeatWindow.window_sequence.desc())
                    .limit(max_windows)
                )
            ).scalars().all()

            recent_diagnostics_rows = (
                await session.execute(
                    select(CloudTelemetryDiagnosticEvent)
                    .where(CloudTelemetryDiagnosticEvent.instance_id == instance.id)
                    .order_by(CloudTelemetryDiagnosticEvent.event_at.desc())
                    .limit(max_diagnostics)
                )
            ).scalars().all()

        recent_windows = [
            CloudTelemetryAdminHeartbeatWindowDetail(
                window_sequence=window.window_sequence,
                window_started_at=window.window_started_at,
                window_ended_at=window.window_ended_at,
                received_at=window.received_at,
                status=window.status,
                rejection_type=window.rejection_type,
                payload_bytes=window.payload_bytes,
                diagnostics_count=window.diagnostics_count,
                summary=_decode_window_summary(window.summary_json),
            )
            for window in recent_windows_rows
        ]

        recent_diagnostics = [
            CloudTelemetryAdminDiagnosticEventDetail(
                window_sequence=event.window_sequence,
                event_at=event.event_at,
                received_at=event.received_at,
                severity=event.severity,
                event_name=event.event_name,
                summary=event.summary,
                attributes=_decode_json_object(event.attributes_json),
            )
            for event in recent_diagnostics_rows
        ]

        return CloudTelemetryAdminInstanceDetailResponse(
            client_instance_id=instance.client_instance_id,
            client_instance_id_masked=mask_client_instance_id(
                instance.client_instance_id
            ),
            registration_status=instance.registration_status,
            is_suspended=instance.is_suspended,
            suspended_at=instance.suspended_at,
            suspension_reason=instance.suspension_reason,
            online_status=(snapshot.online_status if snapshot is not None else "offline"),
            online_status_updated_at=(
                snapshot.online_status_updated_at if snapshot is not None else None
            ),
            last_heartbeat_received_at=(
                snapshot.last_heartbeat_received_at if snapshot is not None else None
            ),
            last_success_heartbeat_at=(
                snapshot.last_success_heartbeat_at if snapshot is not None else None
            ),
            last_heartbeat_result=(
                snapshot.last_heartbeat_result if snapshot is not None else None
            ),
            last_heartbeat_interval_seconds=(
                snapshot.last_heartbeat_interval_seconds if snapshot is not None else None
            ),
            offline_deadline_at=(
                snapshot.offline_deadline_at if snapshot is not None else None
            ),
            gap_status=(snapshot.gap_status if snapshot is not None else "healthy"),
            last_window_sequence=(
                snapshot.last_window_sequence if snapshot is not None else None
            ),
            app_version=instance.app_version,
            platform=instance.platform,
            country_code=instance.country_code,
            region_code=instance.region_code,
            allow_ip_retention=instance.allow_ip_retention,
            first_registered_at=instance.first_registered_at,
            last_registered_at=instance.last_registered_at,
            last_diagnostic_severity=(
                snapshot.last_diagnostic_severity if snapshot is not None else None
            ),
            last_diagnostic_at=(
                snapshot.last_diagnostic_at if snapshot is not None else None
            ),
            recent_heartbeat_windows=recent_windows,
            recent_diagnostic_events=recent_diagnostics,
        )

    @staticmethod
    def _require_database():
        """获取数据库管理器，未初始化时抛错。"""

        try:
            return get_cloud_telemetry_database()
        except RuntimeError as exc:
            raise RuntimeError("cloud telemetry database is not initialized") from exc


def _decode_window_summary(summary_json: str) -> dict[str, Any]:
    """Decode stored heartbeat summary defensively for admin responses."""

    return _decode_json_object(summary_json)


def _decode_json_object(raw_json: str) -> dict[str, Any]:
    """Decode a stored JSON object defensively for admin responses."""

    try:
        value = json.loads(raw_json)
    except (TypeError, json.JSONDecodeError):
        logger.warning("failed to decode telemetry json object", exc_info=True)
        return {}

    if isinstance(value, dict):
        return value
    return {}


def _coerce_label(value: Any) -> str:
    """把分组键的 None 与空字符串归一化为 'unknown'。"""

    if value is None:
        return "unknown"
    text = str(value)
    return text if text else "unknown"


async def _find_instance_by_admin_identifier(
    session: Any,
    identifier: str,
) -> CloudTelemetryInstance | None:
    """Find an instance by raw id, with a masked-id fallback for admin UI lists."""

    exact = (
        await session.execute(
            select(CloudTelemetryInstance).where(
                CloudTelemetryInstance.client_instance_id == identifier
            )
        )
    ).scalars().first()
    if exact is not None:
        return exact

    if "***" not in identifier:
        return None

    prefix, suffix = identifier.split("***", 1)
    candidates = (
        await session.execute(
            select(CloudTelemetryInstance).where(
                CloudTelemetryInstance.client_instance_id.like(f"{prefix}%{suffix}")
            )
        )
    ).scalars().all()
    matches = [
        candidate
        for candidate in candidates
        if mask_client_instance_id(candidate.client_instance_id) == identifier
    ]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise LookupError(f"ambiguous masked client_instance_id: {identifier}")
    return None


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _empty_hour_buckets(*, now: float, hours: int = 24) -> list[dict[str, Any]]:
    start = int(now // 3600) * 3600 - (hours - 1) * 3600
    return [{"bucket_at": float(start + i * 3600)} for i in range(hours)]


def _summarize_window_performance(
    windows: list[CloudTelemetryHeartbeatWindow],
    *,
    include_base_urls: bool = True,
) -> dict[str, Any]:
    request_buckets: dict[str, dict[str, Any]] = {}
    latency_weighted = 0.0
    success_weighted = 0.0
    request_count = 0
    total_tokens = 0
    cache_hits = 0.0
    cache_total = 0.0
    payload_bytes = 0
    watchdog_samples = 0
    watchdog_running = 0
    watchdog_thread_alive = 0
    watchdog_registered_streams = 0
    task_active_max = 0
    stream_active_max = 0
    stream_failures_max = 0
    telemetry_domains: dict[str, dict[str, Any]] = {}

    for window in windows:
        payload_bytes += int(window.payload_bytes or 0)
        summary = _decode_window_summary(window.summary_json)
        runtime = summary.get("runtime_health")
        if isinstance(runtime, dict):
            watchdog = runtime.get("watchdog")
            if isinstance(watchdog, dict):
                watchdog_samples += 1
                watchdog_running += 1 if watchdog.get("running") else 0
                watchdog_thread_alive += 1 if watchdog.get("thread_alive") else 0
                watchdog_registered_streams = max(
                    watchdog_registered_streams,
                    _as_int(watchdog.get("registered_streams")),
                )
            task_manager = runtime.get("task_manager")
            if isinstance(task_manager, dict):
                task_active_max = max(
                    task_active_max,
                    _as_int(task_manager.get("active_tasks")),
                )
            stream_loop = runtime.get("stream_loop_manager")
            if isinstance(stream_loop, dict):
                stream_active_max = max(
                    stream_active_max,
                    _as_int(stream_loop.get("active_streams")),
                )
                stream_failures_max = max(
                    stream_failures_max,
                    _as_int(stream_loop.get("total_failures")),
                )

        for domain_item in summary.get("telemetry_domains") or []:
            if not isinstance(domain_item, dict):
                continue
            domain = str(domain_item.get("domain") or "unknown")
            bucket = telemetry_domains.setdefault(
                domain,
                {
                    "domain": domain,
                    "total_events": 0,
                    "error_events": 0,
                    "warning_events": 0,
                    "last_event_at": 0.0,
                },
            )
            bucket["total_events"] += _as_int(domain_item.get("total_events"))
            bucket["error_events"] += _as_int(domain_item.get("error_events"))
            bucket["warning_events"] += _as_int(domain_item.get("warning_events"))
            bucket["last_event_at"] = max(
                _as_float(bucket.get("last_event_at")),
                _as_float(domain_item.get("last_event_at")),
            )

        for item in summary.get("llm_request_name_top") or []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("request_name") or "unknown")
            count = max(0, _as_int(item.get("request_count")))
            tokens = max(0, _as_int(item.get("total_tokens")))
            latency = _as_float(item.get("average_latency"))
            success_rate = _as_float(item.get("success_rate"))
            cache_rate = _as_float(item.get("cache_hit_rate"))
            request_count += count
            total_tokens += tokens
            latency_weighted += latency * count
            success_weighted += success_rate * count
            cache_hits += cache_rate * count
            cache_total += count
            bucket = request_buckets.setdefault(
                name,
                {
                    "request_name": name,
                    "request_count": 0,
                    "total_tokens": 0,
                    "latency_weighted": 0.0,
                    "success_weighted": 0.0,
                    "models": set(),
                    "base_urls": set(),
                    "cache_weighted": 0.0,
                },
            )
            bucket["request_count"] += count
            bucket["total_tokens"] += tokens
            bucket["latency_weighted"] += latency * count
            bucket["success_weighted"] += success_rate * count
            bucket["cache_weighted"] += cache_rate * count
            model = item.get("model_identifier")
            if model:
                bucket["models"].add(str(model))
            for url in item.get("base_urls") or item.get("api_providers") or []:
                if url:
                    bucket["base_urls"].add(str(url))

    top_requests = []
    for bucket in request_buckets.values():
        count = int(bucket["request_count"])
        top_request = {
            "request_name": bucket["request_name"],
            "request_count": count,
            "total_tokens": int(bucket["total_tokens"]),
            "average_latency": bucket["latency_weighted"] / count if count else 0.0,
            "success_rate": bucket["success_weighted"] / count if count else 0.0,
            "cache_hit_rate": bucket["cache_weighted"] / count if count else 0.0,
            "models": sorted(bucket["models"]),
        }
        if include_base_urls:
            top_request["base_urls"] = sorted(bucket["base_urls"])
        top_requests.append(top_request)

    top_requests.sort(key=lambda item: int(item["total_tokens"]), reverse=True)
    health_domains = sorted(
        telemetry_domains.values(),
        key=lambda item: (
            -int(item["error_events"]),
            -int(item["warning_events"]),
            -int(item["total_events"]),
            str(item["domain"]),
        ),
    )
    return {
        "window_count": len(windows),
        "request_count": request_count,
        "total_tokens": total_tokens,
        "average_latency": latency_weighted / request_count if request_count else 0.0,
        "success_rate": success_weighted / request_count if request_count else 0.0,
        "cache_hit_rate": cache_hits / cache_total if cache_total else 0.0,
        "payload_bytes": payload_bytes,
        "watchdog_samples": watchdog_samples,
        "watchdog_running_samples": watchdog_running,
        "watchdog_thread_alive_samples": watchdog_thread_alive,
        "watchdog_registered_streams_max": watchdog_registered_streams,
        "task_active_max": task_active_max,
        "stream_active_max": stream_active_max,
        "stream_failures_max": stream_failures_max,
        "health_domains": health_domains[:12],
        "db_health": telemetry_domains.get(
            "db",
            {
                "domain": "db",
                "total_events": 0,
                "error_events": 0,
                "warning_events": 0,
                "last_event_at": 0.0,
            },
        ),
        "top_requests": top_requests[:10],
    }


def _build_window_timeline(
    windows: list[CloudTelemetryHeartbeatWindow],
    *,
    diagnostics: list[CloudTelemetryDiagnosticEvent] | None = None,
    now: float,
) -> list[dict[str, Any]]:
    buckets = _empty_hour_buckets(now=now)
    by_bucket = {int(item["bucket_at"]): item for item in buckets}
    for item in buckets:
        item.update(
            {
                "windows": 0,
                "payload_bytes": 0,
                "diagnostics": 0,
                "error_events": 0,
                "instances": set(),
            }
        )
    for window in windows:
        bucket_at = int(float(window.received_at) // 3600) * 3600
        bucket = by_bucket.get(bucket_at)
        if bucket is None:
            continue
        bucket["windows"] += 1
        bucket["payload_bytes"] += int(window.payload_bytes or 0)
        bucket["diagnostics"] += int(window.diagnostics_count or 0)
        bucket["instances"].add(int(window.instance_id))
    for diagnostic in diagnostics or []:
        bucket_at = int(float(diagnostic.received_at) // 3600) * 3600
        bucket = by_bucket.get(bucket_at)
        if bucket is None:
            continue
        if str(diagnostic.severity).lower() in {"error", "critical", "fatal"}:
            bucket["error_events"] += 1
    for item in buckets:
        item["instance_count"] = len(item["instances"])
        del item["instances"]
        item["avg_errors_per_heartbeat"] = (
            float(item["error_events"]) / float(item["windows"])
            if item["windows"]
            else 0.0
        )
    return buckets


def _build_diagnostic_timeline(
    diagnostics: list[CloudTelemetryDiagnosticEvent],
    *,
    now: float,
) -> list[dict[str, Any]]:
    buckets = _empty_hour_buckets(now=now)
    by_bucket = {int(item["bucket_at"]): item for item in buckets}
    for item in buckets:
        item.update({"warning": 0, "error": 0, "critical": 0, "info": 0})
    for diagnostic in diagnostics:
        bucket_at = int(float(diagnostic.received_at) // 3600) * 3600
        bucket = by_bucket.get(bucket_at)
        if bucket is None:
            continue
        severity = str(diagnostic.severity or "info").lower()
        if severity not in {"warning", "error", "critical"}:
            severity = "info"
        bucket[severity] += 1
    return buckets


def _build_version_adoption_trend(
    rows: list[Any],
    *,
    now: float,
    days: int,
) -> list[dict[str, Any]]:
    start_day = int(now // 86400) * 86400 - (days - 1) * 86400
    buckets: list[dict[str, Any]] = [
        {"bucket_at": float(start_day + i * 86400), "versions": {}, "total": 0}
        for i in range(days)
    ]
    by_bucket = {int(item["bucket_at"]): item for item in buckets}
    for row in rows:
        registered_at = _as_float(row.first_registered_at, default=0.0)
        bucket_at = int(registered_at // 86400) * 86400
        bucket = by_bucket.get(bucket_at)
        if bucket is None:
            continue
        version = _coerce_label(row.app_version)
        bucket["versions"][version] = int(bucket["versions"].get(version, 0)) + 1
        bucket["total"] += 1
    return buckets
