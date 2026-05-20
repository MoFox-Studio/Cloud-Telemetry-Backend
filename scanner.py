"""云端遥测后台扫描任务。

按 CONTEXT.md「在线状态落盘机制」要求：
- 实例上线状态由注册与成功心跳接入链路同步写入。
- 实例离线状态由后台过期扫描按 offline_deadline_at 落盘更新。
- 整体预览面板优先读取已落盘的在线状态，而不是在查询时临时回算。
"""

from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import update

from .database import get_cloud_telemetry_database
from .models import CloudTelemetryInstanceSnapshot

logger = logging.getLogger("cloud_telemetry_backend.scanner")


class OfflineDeadlineScanner:
    """按 offline_deadline_at 把过期的 active 实例落盘为 offline。"""

    def __init__(self, *, scan_interval_seconds: float) -> None:
        self._scan_interval_seconds = max(1.0, float(scan_interval_seconds))
        self._task: asyncio.Task[None] | None = None
        self._stop_event: asyncio.Event | None = None

    @property
    def running(self) -> bool:
        """返回扫描任务是否在运行。"""

        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        """启动扫描循环。"""

        if self.running:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(
            self._run_loop(), name="cloud_telemetry_offline_scanner"
        )

    async def stop(self) -> None:
        """停止扫描循环。"""

        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            except asyncio.CancelledError:
                pass
            self._task = None
        self._stop_event = None

    async def run_once(self) -> int:
        """执行一次扫描，返回被标记为离线的实例数量。"""

        try:
            database = get_cloud_telemetry_database()
        except RuntimeError:
            return 0

        now = time.time()
        async with database.session() as session:
            statement = (
                update(CloudTelemetryInstanceSnapshot)
                .where(
                    CloudTelemetryInstanceSnapshot.online_status == "active",
                    CloudTelemetryInstanceSnapshot.offline_deadline_at.is_not(None),
                    CloudTelemetryInstanceSnapshot.offline_deadline_at < now,
                )
                .values(
                    online_status="offline",
                    online_status_updated_at=now,
                    updated_at=now,
                )
            )
            result = await session.execute(statement)
            await session.commit()
            return int(result.rowcount or 0)

    async def _run_loop(self) -> None:
        """扫描循环主体。"""

        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                changed = await self.run_once()
                if changed:
                    logger.info("离线扫描：%s 个实例被标记为 offline", changed)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("离线扫描出现异常：%s", exc)

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._scan_interval_seconds,
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise


_global_scanner: OfflineDeadlineScanner | None = None


def init_offline_scanner(*, scan_interval_seconds: float) -> OfflineDeadlineScanner:
    """初始化全局扫描器。"""

    global _global_scanner
    if _global_scanner is not None:
        return _global_scanner
    _global_scanner = OfflineDeadlineScanner(
        scan_interval_seconds=scan_interval_seconds,
    )
    return _global_scanner


def get_offline_scanner() -> OfflineDeadlineScanner | None:
    """返回全局扫描器，未初始化时返回 None。"""

    return _global_scanner


async def close_offline_scanner() -> None:
    """关闭全局扫描器。"""

    global _global_scanner
    if _global_scanner is not None:
        await _global_scanner.stop()
        _global_scanner = None
