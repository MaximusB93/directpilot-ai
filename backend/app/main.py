from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import approvals, audit, auth, clients, health, integrations, recommendations
from app.core.config import settings

app = FastAPI(
    title="DirectPilot AI API",
    description="Backend API for AI-assisted Yandex.Direct audit, recommendations and safe automation.",
    version="0.1.0",
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
app.include_router(auth.router, prefix=settings.api_prefix)
app.include_router(audit.router, prefix=settings.api_prefix)
app.include_router(recommendations.router, prefix=settings.api_prefix)
app.include_router(integrations.router, prefix=settings.api_prefix)
app.include_router(approvals.router, prefix=settings.api_prefix)


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
            f"{settings.api_prefix}/recommendations",
            f"{settings.api_prefix}/integrations",
            f"{settings.api_prefix}/auth/yandex/start",
        ],
    }
