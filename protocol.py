"""云端遥测协议 DTO 定义。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CloudTelemetryProtocolModel(BaseModel):
    """云端遥测协议模型基类。"""

    model_config = ConfigDict(extra="forbid")


class CloudTelemetryChallengeRequest(CloudTelemetryProtocolModel):
    """注册 challenge 请求。"""

    client_instance_id: str = Field(min_length=1)
    app_version: str = Field(min_length=1)
    platform: str = Field(min_length=1)


class CloudTelemetryChallengeResponse(CloudTelemetryProtocolModel):
    """注册 challenge 响应。"""

    challenge_id: str = Field(min_length=1)
    challenge_token: str = Field(min_length=1)
    issued_at: float
    expires_at: float
    server_time: float


class CloudTelemetryRegistrationRequest(CloudTelemetryProtocolModel):
    """安装实例注册请求。"""

    client_instance_id: str = Field(min_length=1)
    challenge_id: str = Field(min_length=1)
    challenge_token: str = Field(min_length=1)
    allow_ip_retention: bool = True
    app_version: str = Field(min_length=1)
    platform: str = Field(min_length=1)


class CloudTelemetryRegistrationResponse(CloudTelemetryProtocolModel):
    """安装实例注册响应。"""

    client_instance_id: str = Field(min_length=1)
    registration_status: Literal["registered"] = "registered"
    install_credential: str = Field(min_length=1)
    credential_issued_at: float
    credential_expires_at: float
    next_window_sequence: int = Field(ge=1)
    next_heartbeat_interval_seconds: int = Field(ge=1)
    server_time: float


class CloudTelemetryHeartbeatDispatchResponse(CloudTelemetryProtocolModel):
    """心跳调度响应。"""

    accepted: bool = True
    next_window_sequence: int = Field(ge=1)
    next_heartbeat_interval_seconds: int = Field(ge=1)
    instance_status: Literal["active", "suspended"] = "active"
    server_time: float


class CloudTelemetryDiagnosticEventPayload(CloudTelemetryProtocolModel):
    """受控诊断事件载荷。"""

    event_name: str = Field(min_length=1)
    severity: Literal["info", "warning", "error", "critical"]
    event_at: float
    summary: str = ""
    attributes: dict[str, Any] = Field(default_factory=dict)


class CloudTelemetryHeartbeatWindowPayload(CloudTelemetryProtocolModel):
    """单个心跳窗口载荷。"""

    window_sequence: int = Field(ge=1)
    window_started_at: float
    window_ended_at: float
    payload_bytes: int = Field(default=0, ge=0)
    summary: dict[str, Any] = Field(default_factory=dict)
    diagnostic_events: list[CloudTelemetryDiagnosticEventPayload] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_window_time(self) -> "CloudTelemetryHeartbeatWindowPayload":
        """校验窗口时间范围。"""

        if self.window_ended_at < self.window_started_at:
            raise ValueError("window_ended_at must be greater than or equal to window_started_at")
        return self


class CloudTelemetryBatchHeartbeatRequest(CloudTelemetryProtocolModel):
    """批量心跳请求。"""

    request_id: str = Field(min_length=1)
    client_instance_id: str = Field(min_length=1)
    install_credential: str = Field(min_length=1)
    windows: list[CloudTelemetryHeartbeatWindowPayload] = Field(min_length=1)
    sent_at: float | None = None

    @model_validator(mode="after")
    def validate_unique_window_sequences(self) -> "CloudTelemetryBatchHeartbeatRequest":
        """校验窗口序号不重复。"""

        sequences = [window.window_sequence for window in self.windows]
        if len(sequences) != len(set(sequences)):
            raise ValueError("duplicate window_sequence detected")
        return self


class CloudTelemetryHeartbeatWindowAck(CloudTelemetryProtocolModel):
    """逐窗口确认结果。"""

    window_sequence: int = Field(ge=1)
    status: Literal["accepted", "duplicate", "rejected_retryable", "rejected_permanent"]
    reason: str | None = None


class CloudTelemetryBatchHeartbeatResponse(CloudTelemetryProtocolModel):
    """批量心跳响应。"""

    request_id: str = Field(min_length=1)
    accepted_window_count: int = Field(ge=0)
    duplicate_window_count: int = Field(ge=0)
    rejected_window_count: int = Field(ge=0)
    window_results: list[CloudTelemetryHeartbeatWindowAck]
    next_window_sequence: int = Field(ge=1)
    next_heartbeat_interval_seconds: int = Field(ge=1)
    instance_status: Literal["active", "suspended"] = "active"
    server_time: float


class CloudTelemetryAdminStatusResponse(CloudTelemetryProtocolModel):
    """管理状态响应。"""

    service: Literal["cloud_telemetry"] = "cloud_telemetry"
    ingest_prefix: str = Field(min_length=1)
    protected_admin_routes: list[str]


# ===== 后台管理接口 DTO =====


class CloudTelemetryAdminInstanceSummary(CloudTelemetryProtocolModel):
    """整体预览列表返回的单实例摘要。"""

    client_instance_id_masked: str
    online_status: str
    last_heartbeat_received_at: float | None = None
    last_success_heartbeat_at: float | None = None
    last_window_sequence: int | None = None
    gap_status: str
    is_suspended: bool
    app_version: str | None = None
    platform: str | None = None
    country_code: str | None = None
    region_code: str | None = None
    last_diagnostic_severity: str | None = None
    last_diagnostic_at: float | None = None
    first_registered_at: float | None = None


class CloudTelemetryAdminInstanceListResponse(CloudTelemetryProtocolModel):
    """整体预览分页列表响应。"""

    total_count: int = Field(ge=0)
    items: list[CloudTelemetryAdminInstanceSummary]
    offset: int = Field(ge=0)
    limit: int = Field(ge=1)


class CloudTelemetryAdminOverviewSummaryResponse(CloudTelemetryProtocolModel):
    """整体预览摘要响应。"""

    total_instances: int = Field(ge=0)
    online_instances: int = Field(ge=0)
    offline_instances: int = Field(ge=0)
    suspended_instances: int = Field(ge=0)
    gap_status_breakdown: dict[str, int]
    platform_breakdown: dict[str, int]
    country_breakdown: dict[str, int]
    server_time: float


class CloudTelemetryAdminHeartbeatWindowDetail(CloudTelemetryProtocolModel):
    """单实例详情中的心跳窗口明细。"""

    window_sequence: int
    window_started_at: float
    window_ended_at: float
    received_at: float
    status: str
    rejection_type: str | None = None
    payload_bytes: int
    diagnostics_count: int
    summary: dict[str, Any] = Field(default_factory=dict)


class CloudTelemetryAdminDiagnosticEventDetail(CloudTelemetryProtocolModel):
    """单实例详情中的诊断事件。"""

    window_sequence: int | None = None
    event_at: float
    received_at: float
    severity: str
    event_name: str
    summary: str
    attributes: dict[str, Any] = Field(default_factory=dict)


class CloudTelemetryAdminInstanceDetailResponse(CloudTelemetryProtocolModel):
    """单实例详情响应。"""

    client_instance_id: str
    client_instance_id_masked: str
    registration_status: str
    is_suspended: bool
    suspended_at: float | None = None
    suspension_reason: str | None = None
    online_status: str
    online_status_updated_at: float | None = None
    last_heartbeat_received_at: float | None = None
    last_success_heartbeat_at: float | None = None
    last_heartbeat_result: str | None = None
    last_heartbeat_interval_seconds: int | None = None
    offline_deadline_at: float | None = None
    gap_status: str
    last_window_sequence: int | None = None
    app_version: str | None = None
    platform: str | None = None
    country_code: str | None = None
    region_code: str | None = None
    allow_ip_retention: bool
    first_registered_at: float | None = None
    last_registered_at: float | None = None
    last_diagnostic_severity: str | None = None
    last_diagnostic_at: float | None = None
    recent_heartbeat_windows: list[CloudTelemetryAdminHeartbeatWindowDetail]
    recent_diagnostic_events: list[CloudTelemetryAdminDiagnosticEventDetail]
