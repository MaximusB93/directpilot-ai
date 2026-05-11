from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import audit, clients, health, integrations, recommendations
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
app.include_router(audit.router, prefix=settings.api_prefix)
app.include_router(recommendations.router, prefix=settings.api_prefix)
app.include_router(integrations.router, prefix=settings.api_prefix)
