from __future__ import annotations

from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_session_user
from app.db import get_optional_db
from app.models import ClientAccount
from app.services.business_context_autofill import build_business_context_autofill

router = APIRouter(prefix="/clients", tags=["business-context"])


class BusinessContextAutofillRequest(BaseModel):
    urls: list[str] = Field(min_length=1, max_length=5)


class BusinessContextAutofillSource(BaseModel):
    url: str
    finalUrl: str | None = None
    statusCode: int | None = None
    title: str | None = None
    textLength: int = 0
    contentLength: int = 0
    contentSample: str | None = None
    extractionMethod: str | None = None
    error: str | None = None


class BusinessContextAutofillResponse(BaseModel):
    draft: dict[str, str | None]
    sources: list[BusinessContextAutofillSource]
    warnings: list[str] = []


def _require_db(db: Session | None) -> Session:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL is required to use business context autofill.",
        )
    return db


def _get_owned_client(db: Session, client_id: str, current: CurrentUser) -> ClientAccount:
    client = db.get(ClientAccount, client_id)
    if not client or client.organization_id != current.organization.id:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


@router.post("/{client_id}/business-context/autofill", response_model=BusinessContextAutofillResponse)
async def autofill_client_business_context(
    client_id: str,
    payload: BusinessContextAutofillRequest,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> BusinessContextAutofillResponse:
    db = _require_db(db)
    client = _get_owned_client(db, client_id, current)
    result = await build_business_context_autofill(client.name, payload.urls)
    return BusinessContextAutofillResponse(**result)
