from __future__ import annotations

import httpx
import pytest

from cloud_telemetry_backend.frontend import render_frontend_asset


def test_frontend_assets_are_readable_from_package() -> None:
    css = render_frontend_asset("telemetry.css")
    js = render_frontend_asset("telemetry.js")
    logo = render_frontend_asset("logo.png")

    assert "text/css" in (css.media_type or "")
    assert "application/javascript" in (js.media_type or "")
    assert "image/png" in (logo.media_type or "")
    assert b".telemetry-app" in css.body
    assert b"apiPrefix" in js.body
    assert len(logo.body) > 10000


@pytest.mark.asyncio
async def test_logo_endpoints(telemetry_client: httpx.AsyncClient) -> None:
    # Test both direct prefix and assets subdirectory paths
    res1 = await telemetry_client.get("/_cloud_telemetry/logo.png")
    assert res1.status_code == 200
    assert "image/png" in res1.headers.get("content-type", "")
    assert len(res1.content) > 10000

    res2 = await telemetry_client.get("/_cloud_telemetry/assets/logo.png")
    assert res2.status_code == 200
    assert "image/png" in res2.headers.get("content-type", "")
    assert len(res2.content) > 10000

