import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.access import router as access_router
from app.api.auth import router as auth_router
from app.api.gateway import router as gateway_router
from app.api.health import router
from app.api.model_catalog import router as model_router
from app.api.organization import router as organization_router
from app.core.config import Settings
from app.core.errors import register_exception_handlers
from app.core.logging import RequestLoggingMiddleware, configure_logging
from app.db.cache import create_redis_client
from app.db.postgres import create_database_engine, create_session_factory
from app.integrations.gateway_proxy import proxy_client
from app.repositories.health import HealthRepository
from app.services.gateway_recovery import recover
from app.services.health import HealthService


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        configure_logging(config.app_log_level)
        database = create_database_engine(config)
        cache = create_redis_client(config)
        application.state.settings = config
        application.state.database = database
        application.state.session_factory = create_session_factory(database)
        application.state.cache = cache
        application.state.health_service = HealthService(
            HealthRepository(database, cache), config.app_probe_timeout
        )
        try:
            async with proxy_client() as gateway_http:
                application.state.gateway_http = gateway_http
                recovery = asyncio.create_task(
                    recover(application.state.session_factory, cache, config.app_gateway_deadline)
                )
                try:
                    yield
                finally:
                    recovery.cancel()
                    with suppress(asyncio.CancelledError):
                        await recovery
        finally:
            try:
                await cache.aclose()
            finally:
                await database.dispose()

    application = FastAPI(
        title=config.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if config.app_docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.app_docs_enabled else None,
    )
    register_exception_handlers(application)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=config.app_cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=["X-Request-ID"],
    )
    application.add_middleware(RequestLoggingMiddleware)
    application.include_router(router)
    application.include_router(auth_router)
    application.include_router(organization_router)
    application.include_router(model_router)
    application.include_router(access_router)
    application.include_router(gateway_router)
    return application


app = create_app()
