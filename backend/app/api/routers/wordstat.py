from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_session_user
from app.connectors.yandex_wordstat import YandexWordstatConnector
from app.core.config import settings
from app.db import get_db
from app.services.connected_accounts import get_latest_yandex_access_token
from app.services.wordstat_dynamics import WordstatDynamicsService

router = APIRouter(prefix="/wordstat", tags=["wordstat"])


class WordstatConnectionCheck(BaseModel):
    configured: bool
    can_call_api: bool
    provider: str
    message: str


class WordstatDynamicsBatchRequest(BaseModel):
    phrases: list[str] = Field(min_length=1, max_length=50)
    period: str = "MONTHLY"
    fromDate: date
    toDate: date
    regions: list[str] = Field(default_factory=list, max_length=100)
    devices: list[str] = Field(default_factory=lambda: ["DEVICE_ALL"], max_length=3)
    clientId: str | None = None
    forceRefresh: bool = False


class WordstatDynamicsSingleRequest(BaseModel):
    phrase: str = Field(min_length=1, max_length=400)
    period: str = "MONTHLY"
    fromDate: date
    toDate: date
    regions: list[str] = Field(default_factory=list, max_length=100)
    devices: list[str] = Field(default_factory=lambda: ["DEVICE_ALL"], max_length=3)
    clientId: str | None = None
    forceRefresh: bool = False


def _wordstat_connector(db: Session) -> YandexWordstatConnector:
    token = get_latest_yandex_access_token(db)
    return YandexWordstatConnector(
        api_key=settings.yandex_search_api_key,
        access_token=token,
        folder_id=settings.yandex_search_folder_id,
    )


@router.get("/connection", response_model=WordstatConnectionCheck)
def check_wordstat_connection(
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> WordstatConnectionCheck:
    token = get_latest_yandex_access_token(db)
    configured = bool(settings.yandex_search_api_key or token)
    folder_note = " Folder ID is configured." if settings.yandex_search_folder_id else " Folder ID is not configured; API may reject requests if your Search API setup requires it."
    return WordstatConnectionCheck(
        configured=configured,
        can_call_api=configured,
        provider="yandex_search_api",
        message=(
            "Wordstat/Search API credentials are available." + folder_note
            if configured
            else "Connect a Yandex account or set YANDEX_SEARCH_API_KEY before requesting Wordstat data."
        ),
    )


@router.post("/dynamics", response_model=dict[str, Any])
def get_wordstat_dynamics(
    request: WordstatDynamicsSingleRequest,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> dict[str, Any]:
    batch_request = WordstatDynamicsBatchRequest(
        phrases=[request.phrase],
        period=request.period,
        fromDate=request.fromDate,
        toDate=request.toDate,
        regions=request.regions,
        devices=request.devices,
        clientId=request.clientId,
        forceRefresh=request.forceRefresh,
    )
    return get_wordstat_dynamics_batch(batch_request, db, current)


@router.post("/dynamics/batch", response_model=dict[str, Any])
def get_wordstat_dynamics_batch(
    request: WordstatDynamicsBatchRequest,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> dict[str, Any]:
    connector = _wordstat_connector(db)
    if not connector.is_configured:
        raise HTTPException(status_code=404, detail="Connect a Yandex account or set YANDEX_SEARCH_API_KEY before requesting Wordstat data.")
    try:
        return WordstatDynamicsService(db, connector).get_batch_dynamics(
            phrases=request.phrases,
            period=request.period,
            from_date=request.fromDate,
            to_date=request.toDate,
            regions=request.regions,
            devices=request.devices,
            organization_id=current.organization_id,
            client_id=request.clientId,
            force_refresh=request.forceRefresh,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
