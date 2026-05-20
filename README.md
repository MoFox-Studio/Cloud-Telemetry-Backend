# Cloud Telemetry Backend

独立云端遥测接入与后台只读管理服务。

按 [Neo-MoFox/CONTEXT.md](../Neo-MoFox/CONTEXT.md) 中「云端遥测」相关领域词汇实现。

## 功能范围

- 接入层：注册引导 challenge → 安装实例注册 → 上线心跳 → 批量心跳。
- 心跳处理：逐窗口幂等去重、心跳缺口状态、实例级停传分流。
- 来源 IP 与地域派生：基于 MaxMind GeoLite2 数据库派生粗粒度国家/地区 + 省/州。
- 状态快照层：注册与心跳接入链路同步落盘 online/offline、缺口、停传等当前态。
- 后台扫描：按 `offline_deadline_at` 把过期实例落盘为 offline。
- 后台只读 API：整体预览摘要、整体预览分页列表、单实例详情，全部走 X-API-Key。
- 后台查询审计：所有后台访问写入独立审计表。

## 部署形态

- **Docker 部署（生产）**：默认使用 PostgreSQL，参见 `docker-compose.yml`，连同 PostgreSQL 容器一起拉起。
- **本地测试**：默认使用 SQLite，可直接 `python -m cloud_telemetry_backend` 启动。

## 快速启动（本地，SQLite）

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -e .
cloud-telemetry-backend
```

服务默认监听 `127.0.0.1:8765`，接入前缀 `/_cloud_telemetry`。

健康检查：

```text
GET /_cloud_telemetry/health
```

## Docker 部署（PostgreSQL）

```bash
copy .env.example .env
# 修改 .env 中的 X-API-Key 与 PostgreSQL 密码
docker compose up -d --build
```

`docker-compose.yml` 会拉起 PostgreSQL 容器并自动挂卷，遥测后端容器通过 `depends_on` 等待数据库就绪。

## 配置项

完整环境变量见 `.env.example`，关键项：

| 环境变量 | 用途 |
|----------|------|
| `CLOUD_TELEMETRY_ADMIN_API_KEYS` | 后台 X-API-Key 列表（逗号分隔） |
| `CLOUD_TELEMETRY_BOOTSTRAP_CREDENTIALS` | 注册引导凭证白名单（官方分发预置） |
| `CLOUD_TELEMETRY_DATABASE_TYPE` | `sqlite` 或 `postgresql` |
| `CLOUD_TELEMETRY_GEOIP_DATABASE_PATH` | MaxMind GeoLite2-City.mmdb 路径，留空表示不启用地域派生 |
| `CLOUD_TELEMETRY_OFFLINE_GRACE_FACTOR` | 在线状态判定的宽限系数 |
| `CLOUD_TELEMETRY_OFFLINE_SCAN_INTERVAL_SECONDS` | 后台离线扫描周期 |
| `CLOUD_TELEMETRY_GAP_RECOVERY_WINDOW` | 心跳缺口允许补齐的窗口数（超出视为永久丢失） |

## 后台 API

所有后台接口都受 `X-API-Key` 保护：

```text
GET  /_cloud_telemetry/api/admin/status
GET  /_cloud_telemetry/api/admin/overview/summary
GET  /_cloud_telemetry/api/admin/instances?offset=0&limit=20&...
GET  /_cloud_telemetry/api/admin/instances/{client_instance_id}
```

整体预览列表支持的过滤维度：`online_status`、`platform`、`app_version`、`country_code`、`is_suspended`、`client_instance_id_prefix`。

排序字段白名单：`last_heartbeat_received_at`、`last_success_heartbeat_at`、`first_registered_at`、`last_registered_at`、`online_status`，方向 `asc`/`desc`。

列表接口返回的 `client_instance_id_masked` 默认脱敏（首 8 位 + `***` + 末 4 位）；只有单实例详情接口同时返回原始 `client_instance_id`。

## 测试

```bash
python -m pytest tests
```

测试覆盖：注册流程、challenge 一次性消费、引导凭证白名单、批量心跳幂等、实例级停传、诊断事件白名单、后台分页/排序/过滤、审计写入、离线扫描、GeoIP 解析降级。

## 与客户端的端到端集成测试

仓库另有一个跨包集成测试位于 `Neo-MoFox/test/app/test_cloud_telemetry_backend_integration.py`，
在 Neo-MoFox 仓库中运行 `python -m pytest test/app/test_cloud_telemetry_backend_integration.py` 即可。
