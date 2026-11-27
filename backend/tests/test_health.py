from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings
from app.main import create_app


@asynccontextmanager
async def running_app(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client


async def test_liveness_and_swagger() -> None:
    async with running_app(create_app(Settings(_env_file=None))) as client:
        response = await client.get("/health/live")
        assert response.json() == {"status": "alive"}
        assert response.headers["X-Request-ID"]
        assert (await client.get("/docs")).status_code == 200
        assert "/health/ready" in (await client.get("/openapi.json")).json()["paths"]


async def test_health_endpoints_distinguish_failed_dependencies() -> None:
    app = create_app(Settings(_env_file=None))
    async with running_app(app) as client:
        repository = app.state.health_service.repository
        repository.ping_database = AsyncMock()
        repository.ping_cache = AsyncMock()
        assert (await client.get("/health")).json()["status"] == "ready"

        repository.ping_cache.side_effect = RuntimeError("hidden diagnostic")
        response = await client.get("/health/ready")
        assert response.status_code == 503
        result = response.json()
        assert result["status"] == "not_ready"
        assert result["checks"]["postgresql"]["status"] == "up"
        assert result["checks"]["redis"]["status"] == "down"
        assert "hidden diagnostic" not in response.text
        assert (await client.get("/health/live")).status_code == 200


async def test_cors_and_error_envelope() -> None:
    app = create_app(Settings(_env_file=None, app_cors_origins=["http://localhost:5173"]))
    async with running_app(app) as client:
        response = await client.get("/unknown", headers={"Origin": "http://localhost:5173"})
        assert response.status_code == 404
        assert response.headers["access-control-allow-origin"] == "http://localhost:5173"
        assert response.json()["error"]["code"] == "http_404"
        assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]
