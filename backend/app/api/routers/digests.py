from __future__ import annotations

import hmac
from datetime import date

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_session_user
from app.core.config import settings
from app.db import get_optional_db
from app.models import ClientAccount, MorningDigest
from app.services.morning_digest import (
    default_digest_date,
    digest_to_dict,
    run_digests,
)
from sqlalchemy import select

router = APIRouter(tags=["digests"])


class DigestRunRequest(BaseModel):
    client_id: str | None = None
    digest_date: date | None = None


def _require_db(db: Session | None) -> Session:
    if db is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="DATABASE_URL is required.")
    return db


def _require_cron_secret(authorization: str | None) -> None:
    """Authenticate the scheduler by shared secret only.

    The endpoint deliberately does not care who called it — a cron job, a
    workflow or a person with the secret are all the same. What it does care
    about is that the secret exists: with no secret configured the route would
    be an open trigger, so it refuses to run rather than run unprotected.
    """
    expected = settings.digest_cron_secret
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DIGEST_CRON_SECRET is not configured; scheduled digest runs are disabled.",
        )
    provided = ""
    if authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:].strip()
    # Constant-time comparison: the secret is the only thing guarding the route.
    if not provided or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid digest run secret.")


@router.post("/digests/run")
def run_morning_digests(
    payload: DigestRunRequest | None = None,
    authorization: str | None = Header(default=None),
    db: Session | None = Depends(get_optional_db),
) -> dict:
    _require_cron_secret(authorization)
    db = _require_db(db)
    body = payload or DigestRunRequest()
    return run_digests(db, digest_date=body.digest_date, client_id=body.client_id)


@router.get("/clients/{client_id}/digest")
def get_client_digest(
    client_id: str,
    date: str | None = None,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> dict:
    db = _require_db(db)
    client = db.get(ClientAccount, client_id)
    if not client or client.organization_id != current.organization.id:
        raise HTTPException(status_code=404, detail="Client not found")

    if date:
        try:
            digest_date = _parse_date(date)
        except ValueError:
            raise HTTPException(status_code=422, detail="date must be YYYY-MM-DD") from None
    else:
        digest_date = default_digest_date()

    digest = db.scalar(
        select(MorningDigest).where(
            MorningDigest.client_id == client_id,
            MorningDigest.digest_date == digest_date,
        )
    )
    if digest is None:
        raise HTTPException(status_code=404, detail="Digest not found for this date")
    return digest_to_dict(digest)


def _parse_date(value: str) -> date:
    from datetime import date as _date

    return _date.fromisoformat(value)
