from __future__ import annotations

from cloud_telemetry_backend.frontend import render_frontend_asset


def test_frontend_assets_are_readable_from_package() -> None:
    css = render_frontend_asset("telemetry.css")
    js = render_frontend_asset("telemetry.js")

    assert "text/css" in (css.media_type or "")
    assert "application/javascript" in (js.media_type or "")
    assert b".telemetry-app" in css.body
    assert b"const prefix" in js.body
