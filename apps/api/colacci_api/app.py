"""FastAPI liveness and readiness application for the synthetic review stack."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from time import monotonic

from fastapi import FastAPI, Request, Response, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from apps.api.colacci_api.operations_routes import router as operations_router
from apps.api.colacci_api.review_routes import router as review_router
from apps.api.colacci_api.upload_routes import router as upload_router
from packages.config import Settings
from packages.contracts.health import HealthResponse
from packages.database.health import create_database_engine, database_readiness
from packages.observability.logging import OperationalLogger, normalize_correlation_id


def create_app(settings: Settings | None = None) -> FastAPI:
    configured = settings or Settings()
    logger = OperationalLogger("api", configured.log_level)
    engine = create_database_engine(configured.sqlalchemy_database_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        logger.event(
            "service_started",
            component="http",
            profile=configured.app_profile.value,
            status="up",
            version=configured.app_version,
        )
        try:
            yield
        finally:
            engine.dispose()
            logger.event("service_stopped", component="http", status="stopped")

    app = FastAPI(
        title="Colacci Law Synthetic Review Experience",
        version=configured.app_version,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=lifespan,
    )
    app.state.settings = configured
    app.state.engine = engine
    app.state.operational_logger = logger

    app.add_middleware(
        CORSMiddleware,
        allow_origins=configured.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=[
            "Content-Type",
            "X-Correlation-ID",
            "X-Demo-Principal",
            "X-Demo-Role",
            "X-Demo-Session",
            "X-Client-Submission-ID",
            "X-Generated-Only-Attestation",
            "X-Upload-Direction",
            "X-Upload-Captured-At",
            "X-Upload-Language",
            "X-Upload-Staff-Extension",
        ],
    )

    @app.middleware("http")
    async def operational_request_log(request: Request, call_next: object) -> Response:
        correlation_id = normalize_correlation_id(request.headers.get("X-Correlation-ID"))
        request.state.correlation_id = correlation_id
        started = monotonic()
        response: Response
        try:
            response = await call_next(request)  # type: ignore[operator]
        except Exception:
            logger.event(
                "http_request_failed",
                level="error",
                correlation_id=correlation_id,
                method=request.method,
                route=request.url.path,
                status="internal_error",
            )
            raise
        response.headers["X-Correlation-ID"] = correlation_id
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        logger.event(
            "http_request_completed",
            correlation_id=correlation_id,
            duration_ms=(monotonic() - started) * 1000,
            method=request.method,
            route=request.url.path,
            status=str(response.status_code),
        )
        return response

    @app.get("/health/live", response_model=HealthResponse)
    async def liveness() -> HealthResponse:
        return HealthResponse(
            status="up",
            service="api",
            profile=configured.app_profile.value,
            version=configured.app_version,
            synthetic_data=configured.synthetic_mode,
            database="not_checked",
            migration="not_checked",
        )

    @app.get("/health/ready", response_model=HealthResponse)
    async def readiness() -> HealthResponse | JSONResponse:
        result = database_readiness(engine)
        payload = HealthResponse(
            status="ready" if result.ready else "not_ready",
            service="api",
            profile=configured.app_profile.value,
            version=configured.app_version,
            synthetic_data=configured.synthetic_mode,
            database="ready" if result.connected else "not_ready",
            migration="current" if result.migration_current else "not_current",
        )
        if result.ready:
            return payload
        logger.event(
            "readiness_failed",
            level="warning",
            component="database",
            error_code=result.error_code or "readiness_failed",
            migration_current=result.migration_current,
            status="not_ready",
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload.model_dump(),
        )

    app.include_router(review_router)
    app.include_router(upload_router)
    app.include_router(operations_router)
    return app
