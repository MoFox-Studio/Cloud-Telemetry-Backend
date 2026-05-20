"""客户端实例 ID 外部展示脱敏工具。

按 CONTEXT.md「云端客户端实例 ID 存储」与「客户端实例 ID 展示」要求：
- 服务端内部直接保存原始客户端实例 ID 以支持精确检索。
- 面向外部展示时，客户端实例 ID 应被隐藏或脱敏。
- 客户端实例 ID 不进入公开统计结果。

首版采用「保留前 8 位 + 中间隐藏 + 末 4 位」的展示策略，
单实例详情接口允许同时返回原始 ID 与脱敏 ID 以方便后台运维。
"""

from __future__ import annotations


def mask_client_instance_id(
    client_instance_id: str | None,
    *,
    head_chars: int = 8,
    tail_chars: int = 4,
) -> str:
    """对客户端实例 ID 进行脱敏。"""

    if client_instance_id is None:
        return ""
    text = str(client_instance_id)
    if len(text) <= head_chars + tail_chars:
        # 过短的 ID 全部脱敏，避免信息泄漏
        return "*" * len(text)
    return f"{text[:head_chars]}***{text[-tail_chars:]}"
