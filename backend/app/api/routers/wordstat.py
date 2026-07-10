import hashlib
import json
from datetime import date
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_session_user
from app.connectors.yandex_wordstat import YandexWordstatConnector
from app.core.config import DEFAULT_PRODUCTION_AI_MODEL, normalize_ai_request_options, production_ai_model_ids, settings
from app.db import get_db
from app.services.connected_accounts import get_latest_yandex_access_token
from app.services.openrouter import generate_openrouter_response
from app.services.wordstat_dynamics import WordstatDynamicsService, normalize_period

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


class WordstatAiChatMessage(BaseModel):
    role: str
    content: str = Field(min_length=1, max_length=4000)


class WordstatAiChatRequest(BaseModel):
    question: str = Field(min_length=2, max_length=4000)
    wordstat: dict[str, Any]
    comparison: dict[str, Any] | None = None
    history: list[WordstatAiChatMessage] = Field(default_factory=list, max_length=8)
    model: str | None = None
    ai_preset: str | None = "economy"
    max_tokens: int | None = Field(default=None, ge=500, le=5000)


def _wordstat_connector(db: Session, organization_id: str | None = None) -> YandexWordstatConnector:
    token = get_latest_yandex_access_token(db, organization_id=organization_id)
    return YandexWordstatConnector(
        api_key=settings.yandex_search_api_key,
        access_token=token,
        folder_id=settings.yandex_search_folder_id,
    )


def _mask_secret(value: str | None) -> dict[str, Any]:
    if not value:
        return {
            "configured": False,
            "length": 0,
            "prefix": None,
            "suffix": None,
            "sha256_12": None,
        }
    return {
        "configured": True,
        "length": len(value),
        "prefix": value[:6],
        "suffix": value[-6:],
        "sha256_12": hashlib.sha256(value.encode("utf-8")).hexdigest()[:12],
    }


def _sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    sanitized = dict(headers)
    auth = sanitized.get("Authorization")
    if auth:
        scheme, _, secret = auth.partition(" ")
        masked = _mask_secret(secret)
        sanitized["Authorization"] = f"{scheme} {masked['prefix']}...{masked['suffix']} sha256_12={masked['sha256_12']} len={masked['length']}"
    return sanitized


def _wordstat_error_body(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def _compact_wordstat_payload(value: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    compact = {
        "status": value.get("status"),
        "meta": value.get("meta"),
        "summary": value.get("summary"),
    }
    compact_series = []
    for series in list(value.get("series") or [])[:20]:
        points = list(series.get("points") or [])
        compact_series.append(
            {
                "phrase": series.get("phrase"),
                "source": series.get("source"),
                "error": series.get("error"),
                "pointsCount": len(points),
                "points": points[:80],
            }
        )
    compact["series"] = compact_series
    return compact


def _build_wordstat_ai_prompt(payload: WordstatAiChatRequest) -> str:
    current = _compact_wordstat_payload(payload.wordstat)
    comparison = _compact_wordstat_payload(payload.comparison)
    history = [item.model_dump() for item in payload.history[-6:]]
    return f"""Ты senior PPC/SEO-аналитик. Проанализируй данные Yandex Wordstat Dynamics, которые пользователь только что запросил в DirectPilot AI.

Правила ответа:
- Пиши по-русски, кратко, но по делу.
- Отделяй факты от гипотез.
- Не выдумывай данные, которых нет в payload.
- Учитывай период, группировку, регионы, устройства, фразы, суммы, MoM/YoY/index, сравнение периодов, если оно есть.
- Давай практические выводы для маркетинга/контекстной рекламы/SEO: спрос, сезонность, тренд, какие фразы сильнее, где нужна проверка.
- Если данных мало, прямо скажи об ограничениях.
- Не предлагай автоматически менять рекламные кампании; только рекомендации для ручной проверки.

Вопрос пользователя:
{payload.question}

История чата:
{json.dumps(history, ensure_ascii=False)}

Текущий Wordstat payload:
{json.dumps(current, ensure_ascii=False)}

Payload сравнения:
{json.dumps(comparison, ensure_ascii=False) if comparison else "null"}
"""


@router.get("/connection", response_model=WordstatConnectionCheck)
def check_wordstat_connection(
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> WordstatConnectionCheck:
    token = get_latest_yandex_access_token(db, organization_id=current.organization.id)
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


@router.get("/debug", response_model=dict[str, Any])
def debug_wordstat_connection(
    phrase: str = "купить диван",
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> dict[str, Any]:
    token = get_latest_yandex_access_token(db, organization_id=current.organization.id)
    connector = YandexWordstatConnector(
        api_key=settings.yandex_search_api_key,
        access_token=token,
        folder_id=settings.yandex_search_folder_id,
        timeout_seconds=20,
    )
    auth_mode = "api_key" if settings.yandex_search_api_key else "oauth" if token else "none"
    period = normalize_period("MONTHLY")
    from_date = date(2026, 1, 1)
    to_date = date(2026, 3, 31)

    diagnostics: dict[str, Any] = {
        "provider": "yandex_search_api",
        "authMode": auth_mode,
        "apiKey": _mask_secret(settings.yandex_search_api_key),
        "oauthTokenFromDb": _mask_secret(token),
        "folderId": settings.yandex_search_folder_id,
        "organizationId": current.organization.id,
        "currentUserEmail": current.email,
        "testRequest": {
            "phrase": phrase,
            "period": period,
            "fromDate": from_date.isoformat(),
            "toDate": to_date.isoformat(),
            "regions": ["225"],
            "devices": ["DEVICE_ALL"],
        },
    }

    if not connector.is_configured:
        diagnostics["result"] = {"ok": False, "error": "No API key or OAuth token configured."}
        return diagnostics

    payload: dict[str, Any] = {
        "phrase": phrase,
        "period": period,
        "fromDate": "2026-01-01T00:00:00Z",
        "toDate": "2026-03-31T23:59:59Z",
        "regions": ["225"],
        "devices": ["DEVICE_ALL"],
    }
    if settings.yandex_search_folder_id:
        payload["folderId"] = settings.yandex_search_folder_id

    headers = connector._headers()  # noqa: SLF001 - debug endpoint intentionally shows sanitized effective headers
    diagnostics["effectiveRequest"] = {
        "url": connector.dynamics_url,
        "payload": payload,
        "headers": _sanitize_headers(headers),
    }

    try:
        response = httpx.post(connector.dynamics_url, json=payload, headers=headers, timeout=20)
        diagnostics["result"] = {
            "ok": response.status_code == 200,
            "httpStatus": response.status_code,
            "body": _wordstat_error_body(response),
        }
    except Exception as exc:  # noqa: BLE001 - diagnostics should return the failure
        diagnostics["result"] = {"ok": False, "exception": str(exc)}

    return diagnostics


@router.post("/ai-chat", response_model=dict[str, Any])
async def chat_with_wordstat_ai(
    payload: WordstatAiChatRequest,
    current: CurrentUser = Depends(get_current_session_user),
) -> dict[str, Any]:
    ai_options = normalize_ai_request_options(
        model=payload.model,
        ai_preset=payload.ai_preset,
        max_tokens=payload.max_tokens,
        models=production_ai_model_ids(),
        configured_default=DEFAULT_PRODUCTION_AI_MODEL,
        production_only=True,
    )
    prompt = _build_wordstat_ai_prompt(payload)
    selected_model = str(ai_options["model"])
    try:
        result = await generate_openrouter_response(
            model=selected_model,
            prompt=prompt,
            max_tokens=int(ai_options["max_tokens"]),
        )
    except HTTPException:
        raise
    return {
        "answer": result.get("content") or "",
        "model": result.get("model") or selected_model,
        "usage": result.get("usage"),
        "source": "wordstat_openrouter_analysis",
    }


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
    connector = _wordstat_connector(db, organization_id=current.organization.id)
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
            organization_id=current.organization.id,
            client_id=request.clientId,
            force_refresh=request.forceRefresh,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
