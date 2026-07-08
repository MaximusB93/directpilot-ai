from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routers import ai, approvals, audit, auth, business_context, clients, debug, health, integrations, performance_range, recommendations, wordstat, yandex_direct
from app.core.config import settings
from app.db import init_db
from app.services.token_crypto import OAuthTokenDecryptionError

logger = logging.getLogger(__name__)


def _safe_startup_error(exc: Exception) -> str:
    message = f"{type(exc).__name__}: {exc}"
    if settings.database_url:
        message = message.replace(settings.database_url, "[DATABASE_URL]")
    return message


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.database_configured = settings.postgres_configured
    app.state.database_initialized = False
    app.state.database_initialization_error = None
    try:
        init_db(run_schema_patch=settings.database_schema_patch_on_startup)
    except Exception as exc:  # pragma: no cover - depends on deployment database availability.
        app.state.database_initialization_error = _safe_startup_error(exc)
        logger.exception(
            "Database initialization failed during startup. "
            "Health endpoints will remain available; DB-backed endpoints may fail."
        )
    else:
        app.state.database_initialized = settings.postgres_configured
    yield


app = FastAPI(
    title="DirectPilot AI API",
    description="Backend API for AI-assisted Yandex.Direct audit, recommendations and safe automation.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(clients.router, prefix=settings.api_prefix)
app.include_router(business_context.router, prefix=settings.api_prefix)
app.include_router(performance_range.router, prefix=settings.api_prefix)
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(audit.router, prefix=settings.api_prefix)
app.include_router(recommendations.router, prefix=settings.api_prefix)
app.include_router(integrations.router, prefix=settings.api_prefix)
app.include_router(approvals.router, prefix=settings.api_prefix)
app.include_router(yandex_direct.router, prefix=settings.api_prefix)
app.include_router(wordstat.router, prefix=settings.api_prefix)
app.include_router(ai.router, prefix=settings.api_prefix)
app.include_router(debug.router, prefix=settings.api_prefix)


@app.exception_handler(OAuthTokenDecryptionError)
async def oauth_token_decryption_exception_handler(
    request: Request,
    exc: OAuthTokenDecryptionError,
) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={
            "detail": str(exc),
            "error_code": "oauth_token_decryption_failed",
            "retryable": False,
        },
    )


@app.get("/", tags=["health"])
def read_root(request: Request) -> dict[str, object]:
    database_error = getattr(request.app.state, "database_initialization_error", None)
    return {
        "status": "degraded" if database_error else "ok",
        "service": settings.service_name,
        "message": "DirectPilot AI backend is running.",
        "database": {
            "configured": settings.postgres_configured,
            "initialized": bool(getattr(request.app.state, "database_initialized", False)),
            "schema_patch_on_startup": settings.database_schema_patch_on_startup,
            "error": database_error,
        },
        "docs_url": "/docs",
        "health_url": "/health",
        "api_prefix": settings.api_prefix,
        "sample_endpoints": [
            f"{settings.api_prefix}/clients",
            f"{settings.api_prefix}/clients/{{client_id}}/business-context/autofill",
            f"{settings.api_prefix}/clients/{{client_id}}/performance-range",
            f"{settings.api_prefix}/clients/{{client_id}}/performance-range/ai-analysis",
            f"{settings.api_prefix}/recommendations",
            f"{settings.api_prefix}/integrations",
            f"{settings.api_prefix}/auth/email/request-code",
            f"{settings.api_prefix}/auth/yandex/start",
            f"{settings.api_prefix}/auth/yandex/status",
            f"{settings.api_prefix}/yandex-direct/connection",
            f"{settings.api_prefix}/yandex-direct/reports/campaigns",
            f"{settings.api_prefix}/wordstat/connection",
            f"{settings.api_prefix}/wordstat/dynamics/batch",
            f"{settings.api_prefix}/ai/openrouter/status",
            f"{settings.api_prefix}/debug/routes",
        ],
    }
