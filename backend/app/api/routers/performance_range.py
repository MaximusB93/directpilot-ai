from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_session_user
from app.db import get_optional_db
from app.models import ClientAccount
from app.services.performance_range import build_live_period_ai_analysis, build_live_period_summary

router = APIRouter(prefix="/clients", tags=["performance-range"])


class PeriodAiAnalysisRequest(BaseModel):
    preset: str = "14d"
    date_from: str | None = None
    date_to: str | None = None
    model: str | None = None
    max_tokens: int = Field(default=3500, ge=1000, le=8000)


def _require_db(db: Session | None) -> Session:
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="DATABASE_URL is required.")
    return db


def _get_owned_client(db: Session, client_id: str, current: CurrentUser) -> ClientAccount:
    client = db.get(ClientAccount, client_id)
    if not client or client.organization_id != current.organization.id:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.get("/{client_id}/performance-range")
def get_client_performance_range(
    client_id: str,
    preset: str = "yesterday",
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> dict:
    db = _require_db(db)
    _get_owned_client(db, client_id, current)
    return build_live_period_summary(db, client_id, preset=preset, date_from=date_from, date_to=date_to)


@router.post("/{client_id}/performance-range/ai-analysis")
async def create_client_performance_range_ai_analysis(
    client_id: str,
    payload: PeriodAiAnalysisRequest,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> dict:
    db = _require_db(db)
    _get_owned_client(db, client_id, current)
    return await build_live_period_ai_analysis(
        db,
        client_id,
        preset=payload.preset,
        date_from=payload.date_from,
        date_to=payload.date_to,
        model=payload.model,
        max_tokens=payload.max_tokens,
    )
