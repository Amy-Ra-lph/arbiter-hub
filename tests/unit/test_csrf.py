import pytest
from httpx import ASGITransport, AsyncClient
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from server.middleware.csrf import CSRFOriginMiddleware


async def _echo(request: Request):
    return JSONResponse({"ok": True})


def _make_app(*, allowed_origins: list[str], auth_mode: str = "oidc"):
    app = Starlette(routes=[
        Route("/test", _echo, methods=["GET", "POST", "PUT", "DELETE"]),
    ])
    app.add_middleware(
        CSRFOriginMiddleware,
        allowed_origins=allowed_origins,
        auth_mode=auth_mode,
    )
    return app


@pytest.mark.asyncio
async def test_post_without_origin_rejected():
    app = _make_app(allowed_origins=["https://hub.example.com"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/test", json={})
        assert resp.status_code == 403
        assert "origin" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_post_with_valid_origin_allowed():
    app = _make_app(allowed_origins=["https://hub.example.com"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/test", json={}, headers={"Origin": "https://hub.example.com"}
        )
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_without_origin_allowed():
    app = _make_app(allowed_origins=["https://hub.example.com"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/test")
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_dev_mode_skips_csrf():
    app = _make_app(allowed_origins=["https://hub.example.com"], auth_mode="dev")
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/test", json={})
        assert resp.status_code == 200


@pytest.mark.asyncio
async def test_post_with_bad_origin_rejected():
    app = _make_app(allowed_origins=["https://hub.example.com"])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/test", json={}, headers={"Origin": "https://evil.com"}
        )
        assert resp.status_code == 403
