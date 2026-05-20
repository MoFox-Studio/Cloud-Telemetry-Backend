"""Small static frontend for cloud telemetry dashboards."""

from __future__ import annotations

from pathlib import Path

from fastapi.responses import HTMLResponse, Response

_STATIC_DIR = Path(__file__).with_name("static")


def _asset_text(name: str) -> str:
    return (_STATIC_DIR / name).read_text(encoding="utf-8")


def render_public_page(prefix: str) -> HTMLResponse:
    return HTMLResponse(_render_shell(prefix=prefix, page="public"))


def render_admin_page(prefix: str) -> HTMLResponse:
    return HTMLResponse(_render_shell(prefix=prefix, page="admin"))


def render_frontend_asset(name: str) -> Response:
    media_type = "text/css" if name.endswith(".css") else "application/javascript"
    return Response(_asset_text(name), media_type=media_type)


def _render_shell(*, prefix: str, page: str) -> str:
    safe_prefix = prefix.rstrip("/") or "/_cloud_telemetry"
    title = "Neo-MoFox Telemetry" if page == "public" else "Telemetry Admin"
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="stylesheet" href="{safe_prefix}/assets/telemetry.css">
  <script defer src="{safe_prefix}/assets/telemetry.js" data-prefix="{safe_prefix}" data-page="{page}"></script>
</head>
<body data-page="{page}">
  <div id="app" class="telemetry-app" data-loading="true"></div>
</body>
</html>"""
