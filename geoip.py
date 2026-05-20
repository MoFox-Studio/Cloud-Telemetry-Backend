"""云端遥测来源 IP 派生为粗粒度地域字段的服务。

按 CONTEXT.md 约束：
- 首版只派生国家/地区与省/州两级粗粒度字段。
- 不派生城市级或经纬度。
- 当 allow_ip_retention 为 False 时，原始 IP 由调用方在派生完成后立即丢弃。
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import logging
import os
from threading import Lock
from typing import Any

logger = logging.getLogger("cloud_telemetry_backend.geoip")


@dataclass(slots=True, frozen=True)
class GeoLookupResult:
    """地域查询结果（粗粒度）。"""

    country_code: str | None
    region_code: str | None


class GeoIPResolver:
    """基于 MaxMind GeoLite2-City 的粗粒度地域解析。

    若数据库路径未配置或缺失，将以禁用状态运行并返回空结果，
    从而保证服务端在无 GeoIP 数据时仍能正常接入心跳。
    """

    def __init__(self, database_path: str | None = None) -> None:
        self._database_path = database_path or ""
        self._reader: Any | None = None
        self._lock = Lock()
        self._initialized = False
        self._enabled = False

    @property
    def enabled(self) -> bool:
        """是否已具备 GeoIP 解析能力。"""

        if not self._initialized:
            self._lazy_initialize()
        return self._enabled

    def lookup(self, source_ip: str | None) -> GeoLookupResult:
        """对来源 IP 进行粗粒度地域解析。"""

        empty = GeoLookupResult(country_code=None, region_code=None)
        if not source_ip:
            return empty

        try:
            address = ipaddress.ip_address(source_ip)
        except ValueError:
            return empty

        if (
            address.is_loopback
            or address.is_private
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
            or address.is_reserved
        ):
            return empty

        if not self.enabled:
            return empty

        try:
            response = self._reader.city(source_ip)  # type: ignore[union-attr]
        except Exception as exc:
            # AddressNotFoundError 等情况降级为空，不抛异常影响接入主链路
            logger.debug("GeoIP 解析失败：%s", exc)
            return empty

        country_code = getattr(getattr(response, "country", None), "iso_code", None)
        subdivision_code: str | None = None
        subdivisions = getattr(response, "subdivisions", None)
        if subdivisions is not None:
            most_specific = getattr(subdivisions, "most_specific", None)
            if most_specific is not None:
                subdivision_code = getattr(most_specific, "iso_code", None)

        return GeoLookupResult(
            country_code=country_code,
            region_code=subdivision_code,
        )

    def close(self) -> None:
        """释放 GeoIP 数据库句柄。"""

        with self._lock:
            if self._reader is not None:
                try:
                    self._reader.close()
                except Exception:
                    pass
            self._reader = None
            self._initialized = False
            self._enabled = False

    def _lazy_initialize(self) -> None:
        """按需加载 GeoIP 数据库。"""

        with self._lock:
            if self._initialized:
                return
            self._initialized = True

            database_path = self._database_path
            if not database_path:
                logger.info(
                    "GeoIP 数据库路径未配置，跳过地域派生（仍可正常接入心跳）"
                )
                return
            if not os.path.exists(database_path):
                logger.warning(
                    "GeoIP 数据库文件不存在：%s，地域字段将保持空", database_path
                )
                return

            try:
                import geoip2.database  # type: ignore[import-not-found]
            except ImportError:
                logger.warning(
                    "未安装 geoip2 依赖，地域字段将保持空。安装命令：pip install geoip2"
                )
                return

            try:
                self._reader = geoip2.database.Reader(database_path)
            except Exception as exc:
                logger.warning("打开 GeoIP 数据库失败：%s", exc)
                return

            self._enabled = True
            logger.info("GeoIP 数据库已加载：%s", database_path)


_global_resolver: GeoIPResolver | None = None


def init_geoip_resolver(database_path: str | None) -> GeoIPResolver:
    """初始化全局 GeoIP 解析器。"""

    global _global_resolver
    if _global_resolver is not None:
        _global_resolver.close()
    _global_resolver = GeoIPResolver(database_path=database_path)
    return _global_resolver


def get_geoip_resolver() -> GeoIPResolver:
    """获取全局 GeoIP 解析器，未初始化时返回禁用实例。"""

    global _global_resolver
    if _global_resolver is None:
        _global_resolver = GeoIPResolver(database_path=None)
    return _global_resolver


def close_geoip_resolver() -> None:
    """关闭全局 GeoIP 解析器。"""

    global _global_resolver
    if _global_resolver is not None:
        _global_resolver.close()
        _global_resolver = None
