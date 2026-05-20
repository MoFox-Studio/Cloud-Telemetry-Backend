"""后台查询审计写入服务。

按 CONTEXT.md「后台查询审计」「后台查询审计存储」要求：
- 单实例检索、实例详情查看与整体预览面板查询均纳入审计。
- 审计与遥测业务数据共同落在 PostgreSQL 主库，但走独立表集。
- 审计具有独立保留周期与独立访问边界。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from .database import get_cloud_telemetry_database
from .models import CloudTelemetryAdminQueryAudit

logger = logging.getLogger("cloud_telemetry_backend.audit")


async def write_admin_audit(
    *,
    admin_identity: str,
    query_type: str,
    route_path: str,
    target_client_instance_id: str | None,
    source_ip: str | None,
    query_summary: dict[str, Any],
    succeeded: bool = True,
) -> None:
    """写入一条后台查询审计记录。

    任何写入失败都不会影响主请求路径，仅记录到日志中。
    """

    try:
        database = get_cloud_telemetry_database()
    except RuntimeError:
        # 测试环境或数据库未初始化时跳过审计
        return

    try:
        async with database.session() as session:
            session.add(
                CloudTelemetryAdminQueryAudit(
                    occurred_at=time.time(),
                    admin_identity=admin_identity,
                    query_type=query_type,
                    route_path=route_path,
                    target_client_instance_id=target_client_instance_id,
                    query_summary_json=json.dumps(
                        _scrub_summary(query_summary),
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    succeeded=succeeded,
                    source_ip=source_ip,
                )
            )
            await session.commit()
    except Exception as exc:
        logger.warning("写入后台查询审计失败：%s", exc)


def _scrub_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """清理审计摘要中的非法值，保证可 JSON 序列化。"""

    cleaned: dict[str, Any] = {}
    for key, value in summary.items():
        if value is None:
            continue
        if isinstance(value, (str, int, float, bool)):
            cleaned[key] = value
        else:
            cleaned[key] = str(value)
    return cleaned
