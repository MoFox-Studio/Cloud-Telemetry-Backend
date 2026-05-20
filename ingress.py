"""云端遥测 HTTP 接入路由。"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from threading import Lock
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select

from .admin import CloudTelemetryAdminService
from .audit import write_admin_audit
from .challenges import ChallengeStore
from .database import get_cloud_telemetry_database
from .frontend import render_admin_page, render_frontend_asset, render_public_page
from .geoip import get_geoip_resolver
from .models import (
    CloudTelemetryDiagnosticEvent,
    CloudTelemetryHeartbeatWindow,
    CloudTelemetryInstance,
    CloudTelemetryInstanceSnapshot,
)
from .protocol import (
    CloudTelemetryAdminStatusResponse,
    CloudTelemetryBatchHeartbeatRequest,
    CloudTelemetryBatchHeartbeatResponse,
    CloudTelemetryChallengeRequest,
    CloudTelemetryChallengeResponse,
    CloudTelemetryHeartbeatWindowAck,
    CloudTelemetryRegistrationRequest,
    CloudTelemetryRegistrationResponse,
)
from .settings import CloudTelemetryBackendSettings

logger = logging.getLogger("cloud_telemetry_backend.ingress")


def _hash_credential(credential: str) -> str:
    """计算安装实例凭证哈希。"""

    return hashlib.sha256(credential.encode("utf-8")).hexdigest()


def _extract_source_ip(request: Request) -> str | None:
    """从请求中提取客户端来源 IP。

    优先读取 X-Forwarded-For 首段（用于代理场景），否则使用底层连接 IP。
    """

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first = forwarded_for.split(",")[0].strip()
        if first:
            return first
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    if request.client is not None:
        return request.client.host
    return None


class RateLimitError(PermissionError):
    """Raised when a request exceeds an ingress abuse guard."""


@dataclass(slots=True)
class _CounterState:
    window_started_at: float
    count: int = 0


@dataclass(slots=True)
class _FailureState:
    count: int = 0
    cooldown_until: float = 0.0


class IngressAbuseGuard:
    """Small in-memory guard for rate limits and registration failure cooldowns."""

    def __init__(self, settings: CloudTelemetryBackendSettings) -> None:
        self._settings = settings
        self._lock = Lock()
        self._counters: dict[str, _CounterState] = {}
        self._failures: dict[str, _FailureState] = {}

    def check_rate_limit(
        self,
        *,
        source_ip: str | None,
        credential: str | None = None,
    ) -> None:
        now = time.time()
        with self._lock:
            if source_ip:
                self._increment_or_raise(
                    key=f"ip:{source_ip}",
                    now=now,
                    limit=max(1, int(self._settings.ip_rate_limit_per_window)),
                )
            if credential:
                self._increment_or_raise(
                    key=f"credential:{_hash_credential(credential)}",
                    now=now,
                    limit=max(1, int(self._settings.credential_rate_limit_per_window)),
                )

    def check_registration_cooldown(
        self,
        *,
        source_ip: str | None,
        client_instance_id: str | None,
    ) -> None:
        now = time.time()
        with self._lock:
            for key in self._registration_keys(
                source_ip=source_ip,
                client_instance_id=client_instance_id,
            ):
                state = self._failures.get(key)
                if state is not None and state.cooldown_until > now:
                    raise RateLimitError("registration attempts are cooling down")

    def record_registration_failure(
        self,
        *,
        source_ip: str | None,
        client_instance_id: str | None,
    ) -> None:
        now = time.time()
        limit = max(1, int(self._settings.registration_failure_limit))
        cooldown = max(1, int(self._settings.registration_failure_cooldown_seconds))
        with self._lock:
            for key in self._registration_keys(
                source_ip=source_ip,
                client_instance_id=client_instance_id,
            ):
                state = self._failures.setdefault(key, _FailureState())
                if state.cooldown_until and state.cooldown_until <= now:
                    state.count = 0
                    state.cooldown_until = 0.0
                state.count += 1
                if state.count >= limit:
                    state.cooldown_until = now + cooldown

    def record_registration_success(
        self,
        *,
        source_ip: str | None,
        client_instance_id: str | None,
    ) -> None:
        with self._lock:
            for key in self._registration_keys(
                source_ip=source_ip,
                client_instance_id=client_instance_id,
            ):
                self._failures.pop(key, None)

    def _increment_or_raise(self, *, key: str, now: float, limit: int) -> None:
        window = max(1, int(self._settings.rate_limit_window_seconds))
        state = self._counters.get(key)
        if state is None or now - state.window_started_at >= window:
            self._counters[key] = _CounterState(window_started_at=now, count=1)
            return
        state.count += 1
        if state.count > limit:
            raise RateLimitError("rate limit exceeded")

    @staticmethod
    def _registration_keys(
        *,
        source_ip: str | None,
        client_instance_id: str | None,
    ) -> list[str]:
        keys: list[str] = []
        if source_ip:
            keys.append(f"registration_ip:{source_ip}")
        if client_instance_id:
            keys.append(
                f"registration_instance:{_hash_credential(client_instance_id)}"
            )
        return keys


class CloudTelemetryIngressService:
    """云端遥测接入服务。"""

    def __init__(self, settings: CloudTelemetryBackendSettings) -> None:
        self._settings = settings
        self._challenge_store = ChallengeStore(
            ttl_seconds=settings.challenge_ttl_seconds,
        )
        self._abuse_guard = IngressAbuseGuard(settings)

    @property
    def settings(self) -> CloudTelemetryBackendSettings:
        """返回当前生效的设置。"""

        return self._settings

    @property
    def challenge_store(self) -> ChallengeStore:
        """返回 challenge 存储。"""

        return self._challenge_store

    def _get_database_or_none(self):
        """获取云端遥测数据库，未初始化时返回 None。"""

        try:
            return get_cloud_telemetry_database()
        except RuntimeError:
            return None

    def _resolve_geo(self, source_ip: str | None) -> tuple[str | None, str | None]:
        """对来源 IP 派生粗粒度地域字段。"""

        result = get_geoip_resolver().lookup(source_ip)
        return result.country_code, result.region_code

    def _next_interval(self) -> int:
        """返回下一次心跳调度间隔。"""

        return int(self._settings.default_heartbeat_interval_seconds)

    def _offline_deadline(self, now: float) -> float:
        """根据心跳间隔与宽限系数计算下一次离线截止时间。"""

        return now + self._next_interval() * float(self._settings.offline_grace_factor)

    def _credential_expires_at(self, issued_at: float) -> float:
        """Return install credential expiration timestamp."""

        return issued_at + max(1, int(self._settings.install_credential_ttl_seconds))

    @staticmethod
    def _next_window_sequence(snapshot: CloudTelemetryInstanceSnapshot | None) -> int:
        """Return the next globally monotonic heartbeat window sequence."""

        if snapshot is None or snapshot.last_window_sequence is None:
            return 1
        return max(1, int(snapshot.last_window_sequence) + 1)

    def _validate_install_credential(
        self,
        instance: CloudTelemetryInstance,
        install_credential: str,
        *,
        now: float,
    ) -> None:
        """Validate install credential hash and server-side expiration."""

        if instance.credential_hash != _hash_credential(install_credential):
            raise PermissionError("invalid install credential")
        if (
            instance.credential_expires_at is not None
            and float(instance.credential_expires_at) < now
        ):
            raise PermissionError("expired install credential")

    async def issue_challenge(
        self,
        payload: CloudTelemetryChallengeRequest,
        *,
        source_ip: str | None,
    ) -> CloudTelemetryChallengeResponse:
        """生成注册 challenge。"""

        self._abuse_guard.check_rate_limit(
            source_ip=source_ip,
            credential=payload.client_instance_id,
        )
        self._abuse_guard.check_registration_cooldown(
            source_ip=source_ip,
            client_instance_id=payload.client_instance_id,
        )

        challenge = self._challenge_store.issue(
            client_instance_id=payload.client_instance_id,
        )
        return CloudTelemetryChallengeResponse(
            challenge_id=challenge.challenge_id,
            challenge_token=challenge.challenge_token,
            issued_at=challenge.issued_at,
            expires_at=challenge.expires_at,
            server_time=time.time(),
        )

    async def register_instance(
        self,
        payload: CloudTelemetryRegistrationRequest,
        *,
        source_ip: str | None,
    ) -> CloudTelemetryRegistrationResponse:
        """接受安装实例注册。"""

        self._abuse_guard.check_rate_limit(
            source_ip=source_ip,
            credential=payload.client_instance_id,
        )
        self._abuse_guard.check_registration_cooldown(
            source_ip=source_ip,
            client_instance_id=payload.client_instance_id,
        )

        if not self._challenge_store.consume(
            challenge_id=payload.challenge_id,
            challenge_token=payload.challenge_token,
            client_instance_id=payload.client_instance_id,
        ):
            self._abuse_guard.record_registration_failure(
                source_ip=source_ip,
                client_instance_id=payload.client_instance_id,
            )
            raise PermissionError("invalid or expired challenge")

        now = time.time()
        install_credential = f"ctc_{uuid4().hex}"
        credential_expires_at = self._credential_expires_at(now)
        country_code, region_code = self._resolve_geo(source_ip)
        snapshot: CloudTelemetryInstanceSnapshot | None = None

        database = self._get_database_or_none()
        if database is not None:
            async with database.session() as session:
                instance = (
                    await session.execute(
                        select(CloudTelemetryInstance).where(
                            CloudTelemetryInstance.client_instance_id == payload.client_instance_id
                        )
                    )
                ).scalars().first()

                if instance is None:
                    instance = CloudTelemetryInstance(
                        client_instance_id=payload.client_instance_id,
                        registration_status="registered",
                        credential_hash=_hash_credential(install_credential),
                        credential_expires_at=credential_expires_at,
                        app_version=payload.app_version,
                        platform=payload.platform,
                        country_code=country_code,
                        region_code=region_code,
                        allow_ip_retention=payload.allow_ip_retention,
                        is_suspended=False,
                        first_registered_at=now,
                        last_registered_at=now,
                        last_source_ip=source_ip if payload.allow_ip_retention else None,
                        created_at=now,
                        updated_at=now,
                    )
                    session.add(instance)
                    await session.flush()
                else:
                    instance.registration_status = "registered"
                    instance.credential_hash = _hash_credential(install_credential)
                    instance.credential_expires_at = credential_expires_at
                    instance.app_version = payload.app_version
                    instance.platform = payload.platform
                    if country_code is not None:
                        instance.country_code = country_code
                    if region_code is not None:
                        instance.region_code = region_code
                    instance.allow_ip_retention = payload.allow_ip_retention
                    instance.last_registered_at = now
                    instance.last_source_ip = (
                        source_ip if payload.allow_ip_retention else None
                    )
                    instance.updated_at = now

                snapshot = (
                    await session.execute(
                        select(CloudTelemetryInstanceSnapshot).where(
                            CloudTelemetryInstanceSnapshot.instance_id == instance.id
                        )
                    )
                ).scalars().first()
                if snapshot is None:
                    snapshot = CloudTelemetryInstanceSnapshot(
                        instance_id=instance.id,
                        online_status="offline",
                        online_status_updated_at=now,
                        last_heartbeat_result="registered",
                        last_heartbeat_interval_seconds=self._next_interval(),
                        gap_status="healthy",
                        updated_at=now,
                    )
                    session.add(snapshot)
                else:
                    snapshot.online_status = "offline"
                    snapshot.online_status_updated_at = now
                    snapshot.last_heartbeat_result = "registered"
                    snapshot.last_heartbeat_interval_seconds = self._next_interval()
                    snapshot.updated_at = now

                await session.commit()

        self._abuse_guard.record_registration_success(
            source_ip=source_ip,
            client_instance_id=payload.client_instance_id,
        )
        return CloudTelemetryRegistrationResponse(
            client_instance_id=payload.client_instance_id,
            install_credential=install_credential,
            credential_issued_at=now,
            credential_expires_at=credential_expires_at,
            next_window_sequence=self._next_window_sequence(snapshot),
            next_heartbeat_interval_seconds=self._next_interval(),
            server_time=now,
        )
    async def accept_batch_heartbeat(
        self,
        payload: CloudTelemetryBatchHeartbeatRequest,
        *,
        source_ip: str | None,
    ) -> CloudTelemetryBatchHeartbeatResponse:
        """接受批量心跳。"""

        now = time.time()
        country_code, region_code = self._resolve_geo(source_ip)
        database = self._get_database_or_none()
        self._abuse_guard.check_rate_limit(
            source_ip=source_ip,
            credential=payload.install_credential,
        )

        if database is None:
            acks = [
                CloudTelemetryHeartbeatWindowAck(
                    window_sequence=window.window_sequence,
                    status="accepted",
                )
                for window in payload.windows
            ]
            return CloudTelemetryBatchHeartbeatResponse(
                request_id=payload.request_id,
                accepted_window_count=len(acks),
                duplicate_window_count=0,
                rejected_window_count=0,
                window_results=acks,
                next_window_sequence=max(
                    [window.window_sequence for window in payload.windows], default=0
                )
                + 1,
                next_heartbeat_interval_seconds=self._next_interval(),
                server_time=now,
            )

        async with database.session() as session:
            instance = (
                await session.execute(
                    select(CloudTelemetryInstance).where(
                        CloudTelemetryInstance.client_instance_id == payload.client_instance_id
                    )
                )
            ).scalars().first()
            if instance is None:
                raise PermissionError("unknown client instance")
            self._validate_install_credential(
                instance,
                payload.install_credential,
                now=now,
            )

            snapshot = (
                await session.execute(
                    select(CloudTelemetryInstanceSnapshot).where(
                        CloudTelemetryInstanceSnapshot.instance_id == instance.id
                    )
                )
            ).scalars().first()

            # 实例级停传：所有窗口直接返回永久拒绝
            if instance.is_suspended:
                rejection_reason = (
                    instance.suspension_reason or "instance suspended"
                )
                acks = [
                    CloudTelemetryHeartbeatWindowAck(
                        window_sequence=window.window_sequence,
                        status="rejected_permanent",
                        reason=rejection_reason,
                    )
                    for window in payload.windows
                ]
                if snapshot is not None:
                    snapshot.last_heartbeat_received_at = now
                    snapshot.last_heartbeat_result = "rejected_suspended"
                    snapshot.online_status = "suspended"
                    snapshot.online_status_updated_at = now
                    snapshot.updated_at = now
                await session.commit()
                return CloudTelemetryBatchHeartbeatResponse(
                    request_id=payload.request_id,
                    accepted_window_count=0,
                    duplicate_window_count=0,
                    rejected_window_count=len(acks),
                    window_results=acks,
                    next_window_sequence=self._next_window_sequence(snapshot),
                    next_heartbeat_interval_seconds=self._next_interval(),
                    instance_status="suspended",
                    server_time=now,
                )

            if snapshot is None:
                snapshot = CloudTelemetryInstanceSnapshot(
                    instance_id=instance.id,
                    online_status="active",
                    online_status_updated_at=now,
                    gap_status="healthy",
                    updated_at=now,
                )
                session.add(snapshot)
                await session.flush()

            requested_sequences = [window.window_sequence for window in payload.windows]
            existing_sequences = set(
                (
                    await session.execute(
                        select(CloudTelemetryHeartbeatWindow.window_sequence).where(
                            CloudTelemetryHeartbeatWindow.instance_id == instance.id,
                            CloudTelemetryHeartbeatWindow.window_sequence.in_(
                                requested_sequences
                            ),
                        )
                    )
                ).scalars().all()
            )

            last_diagnostic_severity: str | None = snapshot.last_diagnostic_severity
            last_diagnostic_at: float | None = snapshot.last_diagnostic_at
            accepted_window_sequences: list[int] = []
            acks: list[CloudTelemetryHeartbeatWindowAck] = []

            for window in payload.windows:
                if window.window_sequence in existing_sequences:
                    acks.append(
                        CloudTelemetryHeartbeatWindowAck(
                            window_sequence=window.window_sequence,
                            status="duplicate",
                        )
                    )
                    continue

                # 应用诊断事件白名单：只允许已知字段进入 attributes
                whitelisted_diagnostics = [
                    {
                        "event_name": diagnostic.event_name,
                        "severity": diagnostic.severity,
                        "event_at": diagnostic.event_at,
                        "summary": diagnostic.summary,
                        "attributes": _filter_diagnostic_attributes(diagnostic.attributes),
                    }
                    for diagnostic in window.diagnostic_events
                ]

                session.add(
                    CloudTelemetryHeartbeatWindow(
                        instance_id=instance.id,
                        request_id=payload.request_id,
                        window_sequence=window.window_sequence,
                        window_started_at=window.window_started_at,
                        window_ended_at=window.window_ended_at,
                        received_at=now,
                        status="accepted",
                        rejection_type=None,
                        payload_bytes=window.payload_bytes,
                        diagnostics_count=len(whitelisted_diagnostics),
                        summary_json=json.dumps(
                            window.summary, ensure_ascii=False, sort_keys=True
                        ),
                    )
                )
                for diagnostic in whitelisted_diagnostics:
                    session.add(
                        CloudTelemetryDiagnosticEvent(
                            instance_id=instance.id,
                            window_sequence=window.window_sequence,
                            event_at=diagnostic["event_at"],
                            received_at=now,
                            severity=diagnostic["severity"],
                            event_name=diagnostic["event_name"],
                            summary=diagnostic["summary"],
                            attributes_json=json.dumps(
                                diagnostic["attributes"],
                                ensure_ascii=False,
                                sort_keys=True,
                            ),
                        )
                    )
                    last_diagnostic_severity = diagnostic["severity"]
                    last_diagnostic_at = diagnostic["event_at"]

                accepted_window_sequences.append(window.window_sequence)
                acks.append(
                    CloudTelemetryHeartbeatWindowAck(
                        window_sequence=window.window_sequence,
                        status="accepted",
                    )
                )

            # 维护心跳缺口状态
            previous_last_seq = snapshot.last_window_sequence or 0
            new_max_seq = (
                max(accepted_window_sequences)
                if accepted_window_sequences
                else previous_last_seq
            )
            new_gap_status = await self._evaluate_gap_status(
                session=session,
                instance_id=instance.id,
                previous_last_seq=previous_last_seq,
                new_max_seq=new_max_seq,
            )

            if accepted_window_sequences:
                snapshot.last_window_sequence = max(previous_last_seq, new_max_seq)
                snapshot.last_success_heartbeat_at = now
            snapshot.last_heartbeat_received_at = now
            snapshot.last_heartbeat_result = "accepted"
            snapshot.last_heartbeat_interval_seconds = self._next_interval()
            snapshot.online_status = "active"
            snapshot.online_status_updated_at = now
            snapshot.offline_deadline_at = self._offline_deadline(now)
            snapshot.gap_status = new_gap_status
            snapshot.last_diagnostic_severity = last_diagnostic_severity
            snapshot.last_diagnostic_at = last_diagnostic_at
            snapshot.updated_at = now

            instance.updated_at = now
            if country_code is not None:
                instance.country_code = country_code
            if region_code is not None:
                instance.region_code = region_code
            if instance.allow_ip_retention:
                instance.last_source_ip = source_ip
            else:
                instance.last_source_ip = None
            next_window_sequence = self._next_window_sequence(snapshot)
            await session.commit()

        accepted_count = sum(ack.status == "accepted" for ack in acks)
        duplicate_count = sum(ack.status == "duplicate" for ack in acks)
        rejected_count = sum(
            ack.status in {"rejected_retryable", "rejected_permanent"} for ack in acks
        )
        return CloudTelemetryBatchHeartbeatResponse(
            request_id=payload.request_id,
            accepted_window_count=accepted_count,
            duplicate_window_count=duplicate_count,
            rejected_window_count=rejected_count,
            window_results=acks,
            next_window_sequence=next_window_sequence,
            next_heartbeat_interval_seconds=self._next_interval(),
            server_time=now,
        )

    async def _evaluate_gap_status(
        self,
        *,
        session: Any,
        instance_id: int,
        previous_last_seq: int,
        new_max_seq: int,
    ) -> str:
        """评估心跳缺口状态。

        - healthy: 序号连续无缺口。
        - pending: 存在缺口，但仍在补齐窗口范围内。
        - permanent_loss: 缺口已超出补齐窗口，视为永久丢失。
        """

        if new_max_seq <= 0:
            return "healthy"

        # 统计 instance 已接受的全部 window_sequence 数量
        recorded_count = int(
            (
                await session.execute(
                    select(func.count())
                    .select_from(CloudTelemetryHeartbeatWindow)
                    .where(
                        CloudTelemetryHeartbeatWindow.instance_id == instance_id,
                        CloudTelemetryHeartbeatWindow.window_sequence <= new_max_seq,
                    )
                )
            ).scalar_one()
        )

        if recorded_count >= new_max_seq:
            return "healthy"

        # 缺口数量 = 期望序号数 - 已记录数
        gap_count = new_max_seq - recorded_count
        recovery_window = max(1, int(self._settings.gap_recovery_window))
        if gap_count > recovery_window:
            return "permanent_loss"
        return "pending"


def _filter_diagnostic_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    """诊断事件 attributes 白名单收敛。"""

    allowed_keys = {"domain", "entity_id"}
    return {
        key: ("" if value is None else str(value))
        for key, value in attributes.items()
        if key in allowed_keys
    }


class CloudTelemetryIngress:
    """云端遥测 HTTP 接入路由。"""

    def __init__(
        self,
        settings: CloudTelemetryBackendSettings | None = None,
        *,
        admin_dependencies: Sequence[Any] | None = None,
    ) -> None:
        self._mounted = False
        effective_settings = settings or CloudTelemetryBackendSettings.from_env()
        self._settings = effective_settings
        self._service = CloudTelemetryIngressService(effective_settings)
        self._admin_service = CloudTelemetryAdminService(effective_settings)
        self._admin_dependencies = list(admin_dependencies or [])

    @property
    def service(self) -> CloudTelemetryIngressService:
        """返回接入服务。"""

        return self._service

    @property
    def admin_service(self) -> CloudTelemetryAdminService:
        """返回后台只读管理服务。"""

        return self._admin_service

    def set_admin_dependencies(self, dependencies: Sequence[Any] | None) -> None:
        """设置管理接口依赖。"""

        self._admin_dependencies = list(dependencies or [])

    def mount(
        self,
        app: Any,
        prefix: str = "/_cloud_telemetry",
        admin_dependencies: Sequence[Any] | None = None,
    ) -> None:
        """将云端遥测接入路由挂载到 FastAPI 应用。"""

        if admin_dependencies is not None:
            self._admin_dependencies = list(admin_dependencies)
        if self._mounted:
            return
        self._mounted = True
        app.include_router(self._build_router(prefix=prefix), prefix=prefix)

    def _build_router(self, prefix: str) -> APIRouter:
        """构建云端遥测接入路由。"""

        router = APIRouter()
        api_router = APIRouter()
        admin_router = APIRouter(dependencies=self._admin_dependencies)

        @router.get("/health")
        async def health() -> JSONResponse:
            return JSONResponse(
                {
                    "service": "cloud_telemetry",
                    "status": "ok",
                }
            )

        @router.get("/")
        async def public_dashboard():
            return render_public_page(prefix)

        @router.get("/admin")
        async def admin_dashboard():
            return render_admin_page(prefix)

        @router.get("/assets/{asset_name}")
        async def frontend_asset(asset_name: str):
            if asset_name not in {"telemetry.css", "telemetry.js"}:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
            return render_frontend_asset(asset_name)

        @api_router.get("/public/overview")
        async def public_overview() -> JSONResponse:
            try:
                response = await self._admin_service.get_public_overview()
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc),
                ) from exc
            return JSONResponse(response)

        @api_router.post("/register/challenge")
        async def issue_challenge(
            payload: CloudTelemetryChallengeRequest,
            request: Request,
        ) -> JSONResponse:
            try:
                response = await self._service.issue_challenge(
                    payload,
                    source_ip=_extract_source_ip(request),
                )
            except RateLimitError as exc:
                return JSONResponse({"error": str(exc)}, status_code=429)
            except PermissionError as exc:
                return JSONResponse({"error": str(exc)}, status_code=403)
            return JSONResponse(response.model_dump(mode="json"))

        @api_router.post("/register")
        async def register_instance(
            payload: CloudTelemetryRegistrationRequest,
            request: Request,
        ) -> JSONResponse:
            try:
                response = await self._service.register_instance(
                    payload, source_ip=_extract_source_ip(request)
                )
            except RateLimitError as exc:
                return JSONResponse({"error": str(exc)}, status_code=429)
            except PermissionError as exc:
                return JSONResponse({"error": str(exc)}, status_code=403)
            return JSONResponse(response.model_dump(mode="json"))
        @api_router.post("/heartbeats/batch")
        async def batch_heartbeat(
            payload: CloudTelemetryBatchHeartbeatRequest,
            request: Request,
        ) -> JSONResponse:
            try:
                response = await self._service.accept_batch_heartbeat(
                    payload, source_ip=_extract_source_ip(request)
                )
            except RateLimitError as exc:
                return JSONResponse({"error": str(exc)}, status_code=429)
            except PermissionError as exc:
                return JSONResponse({"error": str(exc)}, status_code=403)
            return JSONResponse(response.model_dump(mode="json"))

        @admin_router.get("/admin/status")
        async def admin_status(request: Request) -> JSONResponse:
            response = CloudTelemetryAdminStatusResponse(
                ingest_prefix=prefix,
                protected_admin_routes=[
                    f"{prefix}/api/admin/status",
                    f"{prefix}/api/admin/instances",
                    f"{prefix}/api/admin/instances/{{client_instance_id}}",
                    f"{prefix}/api/admin/overview/summary",
                ],
            )
            await write_admin_audit(
                admin_identity=_resolve_admin_identity(request),
                query_type="admin_status",
                route_path=str(request.url.path),
                target_client_instance_id=None,
                source_ip=_extract_source_ip(request),
                query_summary={},
            )
            return JSONResponse(response.model_dump(mode="json"))

        @admin_router.get("/admin/overview/summary")
        async def admin_overview_summary(request: Request) -> JSONResponse:
            try:
                response = await self._admin_service.get_overview_summary()
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc),
                ) from exc
            await write_admin_audit(
                admin_identity=_resolve_admin_identity(request),
                query_type="overview_summary",
                route_path=str(request.url.path),
                target_client_instance_id=None,
                source_ip=_extract_source_ip(request),
                query_summary={},
            )
            return JSONResponse(response.model_dump(mode="json"))

        @admin_router.get("/admin/diagnostics/summary")
        async def admin_diagnostics_summary(request: Request) -> JSONResponse:
            try:
                response = await self._admin_service.get_admin_diagnostics_summary()
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc),
                ) from exc
            await write_admin_audit(
                admin_identity=_resolve_admin_identity(request),
                query_type="diagnostics_summary",
                route_path=str(request.url.path),
                target_client_instance_id=None,
                source_ip=_extract_source_ip(request),
                query_summary={},
            )
            return JSONResponse(response)

        @admin_router.get("/admin/instances")
        async def admin_list_instances(
            request: Request,
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
        ) -> JSONResponse:
            try:
                response = await self._admin_service.list_instances(
                    offset=offset,
                    limit=limit,
                    online_status=online_status,
                    platform=platform,
                    app_version=app_version,
                    country_code=country_code,
                    is_suspended=is_suspended,
                    client_instance_id_prefix=client_instance_id_prefix,
                    sort_by=sort_by,
                    sort_order=sort_order,
                )
            except ValueError as exc:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(exc),
                ) from exc
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc),
                ) from exc
            await write_admin_audit(
                admin_identity=_resolve_admin_identity(request),
                query_type="instance_list",
                route_path=str(request.url.path),
                target_client_instance_id=None,
                source_ip=_extract_source_ip(request),
                query_summary={
                    "offset": offset,
                    "limit": limit,
                    "online_status": online_status,
                    "platform": platform,
                    "app_version": app_version,
                    "country_code": country_code,
                    "is_suspended": is_suspended,
                    "client_instance_id_prefix": client_instance_id_prefix,
                    "sort_by": sort_by,
                    "sort_order": sort_order,
                },
            )
            return JSONResponse(response.model_dump(mode="json"))

        @admin_router.post("/admin/instances/{client_instance_id}/suspend")
        async def admin_suspend_instance(
            client_instance_id: str,
            request: Request,
        ) -> JSONResponse:
            body = await _read_json_body(request)
            reason = str(body.get("reason") or "manual suspension")
            try:
                response = await self._admin_service.set_instance_suspension(
                    client_instance_id,
                    suspended=True,
                    reason=reason,
                )
            except LookupError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=str(exc),
                ) from exc
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc),
                ) from exc
            await write_admin_audit(
                admin_identity=_resolve_admin_identity(request),
                query_type="instance_suspend",
                route_path=str(request.url.path),
                target_client_instance_id=client_instance_id,
                source_ip=_extract_source_ip(request),
                query_summary={"reason": reason},
            )
            return JSONResponse(response.model_dump(mode="json"))

        @admin_router.post("/admin/instances/{client_instance_id}/resume")
        async def admin_resume_instance(
            client_instance_id: str,
            request: Request,
        ) -> JSONResponse:
            try:
                response = await self._admin_service.set_instance_suspension(
                    client_instance_id,
                    suspended=False,
                )
            except LookupError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=str(exc),
                ) from exc
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc),
                ) from exc
            await write_admin_audit(
                admin_identity=_resolve_admin_identity(request),
                query_type="instance_resume",
                route_path=str(request.url.path),
                target_client_instance_id=client_instance_id,
                source_ip=_extract_source_ip(request),
                query_summary={},
            )
            return JSONResponse(response.model_dump(mode="json"))

        @admin_router.get("/admin/instances/{client_instance_id}")
        async def admin_instance_detail(
            client_instance_id: str,
            request: Request,
        ) -> JSONResponse:
            try:
                response = await self._admin_service.get_instance_detail(client_instance_id)
            except LookupError as exc:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=str(exc),
                ) from exc
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=str(exc),
                ) from exc
            await write_admin_audit(
                admin_identity=_resolve_admin_identity(request),
                query_type="instance_detail",
                route_path=str(request.url.path),
                target_client_instance_id=client_instance_id,
                source_ip=_extract_source_ip(request),
                query_summary={},
            )
            return JSONResponse(response.model_dump(mode="json"))

        router.include_router(api_router, prefix="/api")
        router.include_router(admin_router, prefix="/api")
        return router


def _resolve_admin_identity(request: Request) -> str:
    """从请求中解析后台管理员身份。

    首版采用静态 X-API-Key 方式，未来若引入账号体系再扩展。
    """

    api_key = request.headers.get("x-api-key")
    if not api_key:
        return "anonymous"
    # 用截断哈希作为审计身份，避免在审计日志中明文落库
    digest = hashlib.sha256(api_key.encode("utf-8")).hexdigest()
    return f"static:{digest[:16]}"


async def _read_json_body(request: Request) -> dict[str, Any]:
    try:
        value = await request.json()
    except json.JSONDecodeError:
        return {}
    if isinstance(value, dict):
        return value
    return {}


_ingress: CloudTelemetryIngress | None = None


def get_cloud_telemetry_ingress(
    *,
    settings: CloudTelemetryBackendSettings | None = None,
    admin_dependencies: Sequence[Any] | None = None,
) -> CloudTelemetryIngress:
    """获取全局云端遥测接入单例。"""

    global _ingress
    if _ingress is None:
        _ingress = CloudTelemetryIngress(
            settings=settings,
            admin_dependencies=admin_dependencies,
        )
    elif admin_dependencies is not None:
        _ingress.set_admin_dependencies(admin_dependencies)
    return _ingress
