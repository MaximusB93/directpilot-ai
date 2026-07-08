from fastapi import APIRouter, Request

from app.core.config import settings
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health_check(request: Request) -> HealthResponse:
    database_error = getattr(request.app.state, "database_initialization_error", None)
    return HealthResponse(
        status="degraded" if database_error else "ok",
        service=settings.service_name,
        environment=settings.environment,
        database_configured=settings.postgres_configured,
        database_initialized=bool(getattr(request.app.state, "database_initialized", False)),
        database_error=database_error,
    )
