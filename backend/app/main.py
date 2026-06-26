from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import ai, approvals, audit, auth, business_context, clients, debug, health, integrations, recommendations, wordstat, yandex_direct
from app.core.config import settings
from app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    init_db()
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
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(audit.router, prefix=settings.api_prefix)
app.include_router(recommendations.router, prefix=settings.api_prefix)
app.include_router(integrations.router, prefix=settings.api_prefix)
app.include_router(approvals.router, prefix=settings.api_prefix)
app.include_router(yandex_direct.router, prefix=settings.api_prefix)
app.include_router(wordstat.router, prefix=settings.api_prefix)
app.include_router(ai.router, prefix=settings.api_prefix)
app.include_router(debug.router, prefix=settings.api_prefix)


@app.get("/", tags=["health"])
def read_root() -> dict[str, object]:
    return {
        "status": "ok",
        "service": settings.service_name,
        "message": "DirectPilot AI backend is running.",
        "docs_url": "/docs",
        "health_url": "/health",
        "api_prefix": settings.api_prefix,
        "sample_endpoints": [
            f"{settings.api_prefix}/clients",
            f"{settings.api_prefix}/clients/{{client_id}}/business-context/autofill",
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
