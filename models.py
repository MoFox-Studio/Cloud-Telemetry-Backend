"""云端遥测服务端 ORM 模型定义。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Float, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Mapped, mapped_column

Base = declarative_base()


def get_string_field(*_: Any, **kwargs: Any) -> Text:
    """返回数据库无关的字符串字段类型。"""

    return Text(**kwargs)


class CloudTelemetryInstance(Base):
    """安装实例主表。"""

    __tablename__ = "cloud_telemetry_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_instance_id: Mapped[str] = mapped_column(
        get_string_field(),
        nullable=False,
        unique=True,
        index=True,
        comment="安装实例稳定标识",
    )
    registration_status: Mapped[str] = mapped_column(
        get_string_field(),
        nullable=False,
        default="pending",
        comment="注册状态",
    )
    credential_hash: Mapped[str | None] = mapped_column(
        get_string_field(),
        nullable=True,
        comment="安装实例凭证哈希",
    )
    credential_expires_at: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        default=None,
        comment="credential expiration timestamp",
    )
    app_version: Mapped[str | None] = mapped_column(
        get_string_field(),
        nullable=True,
        comment="客户端版本",
    )
    platform: Mapped[str | None] = mapped_column(
        get_string_field(),
        nullable=True,
        comment="客户端平台",
    )
    country_code: Mapped[str | None] = mapped_column(
        get_string_field(),
        nullable=True,
        comment="粗粒度国家或地区代码",
    )
    region_code: Mapped[str | None] = mapped_column(
        get_string_field(),
        nullable=True,
        comment="粗粒度省州代码",
    )
    allow_ip_retention: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="是否允许长期保留原始来源 IP",
    )
    is_suspended: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment="实例是否已被服务端停传",
    )
    suspended_at: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        default=None,
        comment="停传时间戳",
    )
    suspension_reason: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment="停传原因摘要",
    )
    last_source_ip: Mapped[str | None] = mapped_column(
        get_string_field(),
        nullable=True,
        comment="最近来源 IP（仅在 allow_ip_retention 为 True 时保留）",
    )
    first_registered_at: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        default=None,
        comment="首次注册时间",
    )
    last_registered_at: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        default=None,
        comment="最近注册时间",
    )
    created_at: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="记录创建时间",
    )
    updated_at: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="记录更新时间",
    )

    __table_args__ = (
        Index("idx_cloud_instances_registration_status", "registration_status"),
        Index("idx_cloud_instances_platform", "platform"),
        Index("idx_cloud_instances_version", "app_version"),
        Index("idx_cloud_instances_region", "country_code", "region_code"),
    )


class CloudTelemetryInstanceSnapshot(Base):
    """安装实例当前状态快照表。"""

    __tablename__ = "cloud_telemetry_instance_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("cloud_telemetry_instances.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
        comment="关联安装实例",
    )
    online_status: Mapped[str] = mapped_column(
        get_string_field(),
        nullable=False,
        default="offline",
        comment="在线状态",
    )
    online_status_updated_at: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="在线状态更新时间",
    )
    last_success_heartbeat_at: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        default=None,
        comment="最近一次成功心跳时间",
    )
    last_heartbeat_received_at: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        default=None,
        comment="最近一次接收心跳时间",
    )
    last_heartbeat_result: Mapped[str | None] = mapped_column(
        get_string_field(),
        nullable=True,
        comment="最近一次心跳结果",
    )
    last_heartbeat_interval_seconds: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
        comment="最近一次心跳调度间隔",
    )
    offline_deadline_at: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        default=None,
        comment="离线截止时间",
    )
    gap_status: Mapped[str] = mapped_column(
        get_string_field(),
        nullable=False,
        default="healthy",
        comment="窗口缺口状态",
    )
    last_window_sequence: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
        comment="最近处理的窗口序号",
    )
    last_diagnostic_severity: Mapped[str | None] = mapped_column(
        get_string_field(),
        nullable=True,
        comment="最近诊断事件严重级别",
    )
    last_diagnostic_at: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
        default=None,
        comment="最近诊断事件时间",
    )
    updated_at: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="快照更新时间",
    )

    __table_args__ = (
        Index("idx_cloud_snapshot_online_status", "online_status"),
        Index("idx_cloud_snapshot_offline_deadline", "offline_deadline_at"),
        Index("idx_cloud_snapshot_heartbeat", "last_success_heartbeat_at"),
    )


class CloudTelemetryHeartbeatWindow(Base):
    """心跳窗口事实表。"""

    __tablename__ = "cloud_telemetry_heartbeat_windows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("cloud_telemetry_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联安装实例",
    )
    request_id: Mapped[str | None] = mapped_column(
        get_string_field(),
        nullable=True,
        comment="批量心跳请求标识",
    )
    window_sequence: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="实例内单调递增窗口序号",
    )
    window_started_at: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="窗口起始时间",
    )
    window_ended_at: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="窗口结束时间",
    )
    received_at: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="服务端接收时间",
    )
    status: Mapped[str] = mapped_column(
        get_string_field(),
        nullable=False,
        comment="窗口接收结果",
    )
    rejection_type: Mapped[str | None] = mapped_column(
        get_string_field(),
        nullable=True,
        comment="拒绝类型",
    )
    payload_bytes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="窗口载荷字节数",
    )
    diagnostics_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment="窗口携带诊断事件数量",
    )
    summary_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        comment="窗口摘要 JSON",
    )

    __table_args__ = (
        UniqueConstraint(
            "instance_id",
            "window_sequence",
            name="uq_cloud_heartbeat_instance_sequence",
        ),
        Index("idx_cloud_heartbeat_received", "received_at"),
        Index("idx_cloud_heartbeat_status", "status"),
    )


class CloudTelemetryDiagnosticEvent(Base):
    """诊断事件表。"""

    __tablename__ = "cloud_telemetry_diagnostic_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    instance_id: Mapped[int] = mapped_column(
        ForeignKey("cloud_telemetry_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="关联安装实例",
    )
    window_sequence: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
        default=None,
        comment="来源窗口序号",
    )
    event_at: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="事件发生时间",
    )
    received_at: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="服务端接收时间",
    )
    severity: Mapped[str] = mapped_column(
        get_string_field(),
        nullable=False,
        comment="严重级别",
    )
    event_name: Mapped[str] = mapped_column(
        get_string_field(),
        nullable=False,
        comment="事件名称",
    )
    summary: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
        comment="事件摘要",
    )
    attributes_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        comment="白名单诊断属性 JSON",
    )

    __table_args__ = (
        Index("idx_cloud_diagnostic_event_time", "event_at"),
        Index("idx_cloud_diagnostic_event_severity", "severity"),
        Index("idx_cloud_diagnostic_event_name", "event_name"),
    )


class CloudTelemetryAdminQueryAudit(Base):
    """后台查询审计表。"""

    __tablename__ = "cloud_telemetry_admin_query_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    occurred_at: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        comment="查询发生时间",
    )
    admin_identity: Mapped[str] = mapped_column(
        get_string_field(),
        nullable=False,
        comment="管理员身份标识",
    )
    query_type: Mapped[str] = mapped_column(
        get_string_field(),
        nullable=False,
        comment="查询类型",
    )
    route_path: Mapped[str] = mapped_column(
        get_string_field(),
        nullable=False,
        comment="访问路由",
    )
    target_client_instance_id: Mapped[str | None] = mapped_column(
        get_string_field(),
        nullable=True,
        comment="目标客户端实例 ID",
    )
    query_summary_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="{}",
        comment="查询摘要 JSON",
    )
    succeeded: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        comment="查询是否成功",
    )
    source_ip: Mapped[str | None] = mapped_column(
        get_string_field(),
        nullable=True,
        comment="后台来源 IP",
    )

    __table_args__ = (
        Index("idx_cloud_admin_audit_time", "occurred_at"),
        Index("idx_cloud_admin_audit_admin", "admin_identity"),
        Index("idx_cloud_admin_audit_target", "target_client_instance_id"),
    )
