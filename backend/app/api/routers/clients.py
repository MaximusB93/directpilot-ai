import json
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_session_user
from app.core.config import DEFAULT_PRODUCTION_AI_MODEL, normalize_ai_request_options, production_ai_model_ids, settings
from app.db import get_optional_db
from app.models import (
    ClientAccount,
    ClientBusinessContext,
    ConnectedAccount,
    DirectCampaignPeriodStat,
    DirectReadCache,
    DirectReportJob,
    OAuthToken,
    OptimizationActionDraft as OptimizationActionDraftModel,
    OptimizationActionEvent,
    SyncJob,
)
from app.schemas import (
    AgencyMetric,
    AiClientRecommendationRequest,
    AiChatMessage,
    AiRecommendationResponse,
    Campaign,
    ClientAccountResponse,
    ClientBusinessContextResponse,
    ClientBusinessContextUpdate,
    ClientCreateRequest,
    ClientMemoryNoteCreate,
    ClientYandexBindingRequest,
    ClientYandexBindingStatus,
    ClientYandexIntegrationStatus,
    ClientSummary,
    ClientPerformanceSummaryResponse,
    OptimizationPlanResponse,
    OptimizationActionDraftCreate,
    OptimizationActionDraftListResponse,
    OptimizationActionDraftResponse,
    OptimizationActionDraftUpdateStatus,
    OptimizationActionExecutionPreviewResponse,
    OptimizationActionEventResponse,
    SyncJobResponse,
)
from app.services.ai_chat import build_chat_prompt_debug_snapshot, compact_client_context_for_chat
from app.services.ai_recommendations import (
    build_client_ai_context_from_db,
    build_recommendation_prompt_debug_snapshot,
    generate_client_recommendations_from_context,
)
from app.services.client_sync import list_sync_jobs, run_client_sync
from app.services.connected_accounts import list_yandex_accounts
from app.services.performance_summary import build_optimization_plan, build_performance_summary
from app.services.mock_data import AGENCY_METRICS, CAMPAIGNS, CLIENTS

router = APIRouter(prefix="/clients", tags=["clients"])

ALLOWED_ACTION_TRANSITIONS = {
    "draft": {"reviewed", "approved", "rejected", "needs_changes"},
    "reviewed": {"approved", "rejected", "needs_changes"},
    "needs_changes": {"reviewed", "rejected"},
    "rejected": {"draft"},
    "approved": set(),
}


def _now() -> datetime:
    return datetime.now(UTC)


def _sync_job_response(job) -> SyncJobResponse:
    return SyncJobResponse(
        id=job.id,
        client_id=job.client_id,
        source_type=job.source_type,
        status=job.status,
        period_from=job.period_from.isoformat() if job.period_from else None,
        period_to=job.period_to.isoformat() if job.period_to else None,
        rows_loaded=job.rows_loaded,
        error=job.error,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        created_at=job.created_at.isoformat(),
    )


def _optimization_action_response(action: OptimizationActionDraftModel) -> OptimizationActionDraftResponse:
    return OptimizationActionDraftResponse(
        id=action.id,
        organizationId=action.organization_id,
        clientId=action.client_id,
        source=action.source,
        status=action.status,
        severity=action.severity,
        category=action.category,
        campaignName=action.campaign_name,
        issue=action.issue,
        evidence=action.evidence,
        draftAction=action.draft_action,
        actionType=action.action_type,
        requiresApproval=action.requires_approval,
        canApplyAutomatically=action.can_apply_automatically,
        safetyNote=action.safety_note,
        userComment=action.user_comment,
        createdAt=action.created_at.isoformat(),
        updatedAt=action.updated_at.isoformat() if action.updated_at else None,
        reviewedAt=action.reviewed_at.isoformat() if action.reviewed_at else None,
        approvedAt=action.approved_at.isoformat() if action.approved_at else None,
        rejectedAt=action.rejected_at.isoformat() if action.rejected_at else None,
    )


def _optimization_event_response(event: OptimizationActionEvent) -> OptimizationActionEventResponse:
    return OptimizationActionEventResponse(
        id=event.id,
        actionId=event.action_id,
        organizationId=event.organization_id,
        clientId=event.client_id,
        eventType=event.event_type,
        fromStatus=event.from_status,
        toStatus=event.to_status,
        comment=event.comment,
        createdAt=event.created_at.isoformat(),
    )


def _execution_preview_for_action(action: OptimizationActionDraftModel) -> OptimizationActionExecutionPreviewResponse:
    action_type = (action.action_type or "manual_review").strip() or "manual_review"
    base_required = ["campaign_name", "evidence"]
    missing_data = []
    if not action.campaign_name:
        missing_data.append("campaign_name")
    if not action.evidence:
        missing_data.append("evidence")

    preview_map = {
        "manual_review": {
            "would_do": ["Проверить кампанию вручную", "Сопоставить рекомендацию с фактическими данными клиента"],
            "required_data": base_required,
            "safety_checks": ["Проверка человеком обязательна", "Автоматическое применение отключено"],
            "warnings": ["Автоматическое применение недоступно"],
        },
        "add_negative_keywords": {
            "would_do": ["В будущем могла бы быть подготовлена заявка на добавление минус-фраз"],
            "required_data": ["search query report", "negative keyword list", "match type", *base_required],
            "safety_checks": ["Минус-фразы должны быть проверены человеком", "Нужно убедиться, что минус-фразы не блокируют целевые запросы"],
            "warnings": ["Минус-фразы требуют проверки человеком"],
        },
        "adjust_budget": {
            "would_do": ["В будущем могла бы быть подготовлена корректировка бюджета"],
            "required_data": ["current budget", "target budget", "human confirmation", "date range", *base_required],
            "safety_checks": ["Проверить влияние на расход и лидогенерацию", "Проверить ограничения бюджета и сезонность"],
            "warnings": ["Изменение бюджета может повлиять на расход и лидогенерацию"],
            "missing": ["current budget", "target budget", "date range"],
        },
        "pause_campaign": {
            "would_do": ["В будущем могла бы быть подготовлена остановка кампании"],
            "required_data": ["exact campaign id", "confirmation", "date range", *base_required],
            "safety_checks": ["Проверить, что кампания действительно не приносит целевые конверсии", "Получить явное подтверждение пользователя"],
            "warnings": ["Остановка кампании может остановить лидогенерацию", "Автоматическое применение отключено"],
            "missing": ["exact campaign id", "confirmation", "date range"],
        },
        "change_bid": {
            "would_do": ["В будущем могла бы быть подготовлена корректировка ставки"],
            "required_data": ["current bid", "target bid", "bid strategy context", "human confirmation", *base_required],
            "safety_checks": ["Проверить стратегию ставок и ограничения кампании", "Проверить CPA/ROAS до изменения"],
            "warnings": ["Изменение ставок требует проверки стратегии"],
            "missing": ["current bid", "target bid", "bid strategy context"],
        },
        "improve_ads": {
            "would_do": ["В будущем могли бы быть подготовлены варианты улучшения объявлений"],
            "required_data": ["ad text variants", "landing page context", "moderation constraints", *base_required],
            "safety_checks": ["Проверить тексты объявлений вручную", "Учесть правила модерации Яндекса"],
            "warnings": ["Новые объявления требуют проверки и модерации"],
            "missing": ["ad text variants", "moderation constraints"],
        },
        "tracking_fix": {
            "would_do": ["В будущем могла бы быть подготовлена проверка аналитики и целей"],
            "required_data": ["Metrika counter", "goal ids", "tracking diagnosis", *base_required],
            "safety_checks": ["Проверить корректность целей Метрики", "Не менять аналитику без подтверждения специалиста"],
            "warnings": ["Проверьте корректность целей до изменения аналитики"],
            "missing": ["tracking diagnosis"],
        },
    }
    config = preview_map.get(action_type, preview_map["manual_review"])
    missing_data.extend(item for item in config.get("missing", []) if item not in missing_data)
    if action_type not in preview_map:
        action_type = "unknown"

    return OptimizationActionExecutionPreviewResponse(
        action_id=action.id,
        client_id=action.client_id,
        status=action.status,
        can_preview=True,
        can_apply=False,
        apply_enabled=False,
        action_type=action_type,
        campaign_name=action.campaign_name,
        summary=f"Предпросмотр для черновика: {action.issue}",
        would_do=config["would_do"],
        required_data=config["required_data"],
        missing_data=missing_data,
        safety_checks=[
            *config["safety_checks"],
            "Yandex Direct write API is not called",
            "can_apply=false and apply_enabled=false",
        ],
        warnings=[
            *config["warnings"],
            "Это только предпросмотр. Изменения в Яндекс.Директ не применяются.",
        ],
        next_step="Проверьте данные, комментарий и статус черновика. Реальное применение будет доступно только в будущей approval-based версии.",
    )


def _append_action_event(
    db: Session,
    *,
    action: OptimizationActionDraftModel,
    event_type: str,
    from_status: str | None = None,
    to_status: str | None = None,
    comment: str | None = None,
) -> None:
    db.add(
        OptimizationActionEvent(
            action_id=action.id,
            organization_id=action.organization_id,
            client_id=action.client_id,
            event_type=event_type,
            from_status=from_status,
            to_status=to_status,
            comment=comment,
        )
    )


def _client_response(client: ClientAccount) -> ClientAccountResponse:
    return ClientAccountResponse(
        id=client.id,
        name=client.name,
        segment=client.segment,
        status=client.status,
        directLogin=client.direct_login or "Не подключен",
        metricaCounter=client.metrica_counter or "Не подключен",
        yandexAccountId=client.yandex_account_id,
        targetCpa=client.target_cpa,
        mainGoalId=client.main_goal_id,
        conversionGoalIds=client.conversion_goal_ids,
        notes=client.notes,
        syncStatus=getattr(client, "sync_status", "never_synced"),
        syncError=getattr(client, "sync_error", None),
        lastSyncedAt=client.last_synced_at.isoformat() if getattr(client, "last_synced_at", None) else None,
        syncVersion=getattr(client, "sync_version", 0),
    )


BUSINESS_CONTEXT_FIELD_MAP = {
    "brandName": "brand_name",
    "businessNiche": "business_niche",
    "productSummary": "product_summary",
    "targetAudience": "target_audience",
    "geography": "geography",
    "seasonality": "seasonality",
    "mainOffers": "main_offers",
    "conversionActions": "conversion_actions",
    "averageOrderValue": "average_order_value",
    "leadValueNotes": "lead_value_notes",
    "businessConstraints": "business_constraints",
    "negativeTopics": "negative_topics",
    "landingPageNotes": "landing_page_notes",
    "competitorNotes": "competitor_notes",
    "aiSummary": "ai_summary",
    "manualNotes": "manual_notes",
    "memoryNotes": "memory_notes",
    "sourceNotes": "source_notes",
}


def _business_context_response(context: ClientBusinessContext) -> ClientBusinessContextResponse:
    return ClientBusinessContextResponse(
        id=context.id,
        clientId=context.client_id,
        brandName=context.brand_name,
        businessNiche=context.business_niche,
        productSummary=context.product_summary,
        targetAudience=context.target_audience,
        geography=context.geography,
        seasonality=context.seasonality,
        mainOffers=context.main_offers,
        conversionActions=context.conversion_actions,
        averageOrderValue=context.average_order_value,
        leadValueNotes=context.lead_value_notes,
        businessConstraints=context.business_constraints,
        negativeTopics=context.negative_topics,
        landingPageNotes=context.landing_page_notes,
        competitorNotes=context.competitor_notes,
        aiSummary=context.ai_summary,
        manualNotes=context.manual_notes,
        memoryNotes=context.memory_notes,
        sourceNotes=context.source_notes,
        lastAiUpdateAt=context.last_ai_update_at.isoformat() if context.last_ai_update_at else None,
        createdAt=context.created_at.isoformat() if context.created_at else None,
        updatedAt=context.updated_at.isoformat() if context.updated_at else None,
    )


def _get_or_create_business_context(db: Session, client: ClientAccount) -> ClientBusinessContext:
    context = db.scalar(select(ClientBusinessContext).where(ClientBusinessContext.client_id == client.id))
    if context:
        return context
    context = ClientBusinessContext(client_id=client.id)
    db.add(context)
    db.flush()
    return context


def _require_db(db: Session | None) -> Session:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL is required to persist clients.",
        )
    return db


def _get_owned_client(db: Session, client_id: str, current: CurrentUser) -> ClientAccount:
    client = db.get(ClientAccount, client_id)
    if not client or client.organization_id != current.organization.id:
        raise HTTPException(status_code=404, detail="Client not found")
    return client


def _get_owned_action(
    db: Session,
    client_id: str,
    action_id: str,
    current: CurrentUser,
) -> OptimizationActionDraftModel:
    action = db.get(OptimizationActionDraftModel, action_id)
    if not action or action.client_id != client_id or action.organization_id != current.organization.id:
        raise HTTPException(status_code=404, detail="Optimization action not found")
    return action


@router.get("", response_model=list[ClientAccountResponse])
def list_clients(
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> list[ClientAccountResponse]:
    if db is None:
        return []
    clients = (
        db.query(ClientAccount)
        .filter(ClientAccount.organization_id == current.organization.id)
        .order_by(ClientAccount.created_at.desc())
        .all()
    )
    return [_client_response(client) for client in clients]


@router.post("", response_model=ClientAccountResponse, status_code=status.HTTP_201_CREATED)
def create_client(
    payload: ClientCreateRequest,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> ClientAccountResponse:
    db = _require_db(db)
    client_id = payload.id or str(uuid4())
    existing = db.get(ClientAccount, client_id)
    if existing:
        raise HTTPException(status_code=409, detail="Client already exists")
    client = ClientAccount(
        id=client_id,
        organization_id=current.organization.id,
        name=payload.name.strip(),
        segment=payload.segment or "Клиент",
        direct_login=(payload.direct_login or "").strip() or None,
        metrica_counter=(payload.metrica_counter or "").strip() or None,
        yandex_account_id=None,
        target_cpa=payload.target_cpa,
        main_goal_id=(payload.main_goal_id or "").strip() or None,
        conversion_goal_ids=(payload.conversion_goal_ids or "").strip() or None,
        notes=(payload.notes or "").strip() or None,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return _client_response(client)




@router.put("/{client_id}", response_model=ClientAccountResponse)
def update_client(
    client_id: str,
    payload: ClientCreateRequest,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> ClientAccountResponse:
    db = _require_db(db)
    client = _get_owned_client(db, client_id, current)
    client.name = payload.name.strip()
    client.segment = payload.segment or client.segment
    client.direct_login = (payload.direct_login or "").strip() or None
    client.metrica_counter = (payload.metrica_counter or "").strip() or None
    yandex_account_id = (payload.yandex_account_id or "").strip() or None
    if yandex_account_id:
        account = db.get(ConnectedAccount, yandex_account_id)
        if not account or account.provider != "yandex" or account.organization_id != current.organization.id:
            raise HTTPException(status_code=404, detail="Yandex account not found")
    client.yandex_account_id = yandex_account_id
    client.target_cpa = payload.target_cpa
    client.main_goal_id = (payload.main_goal_id or "").strip() or None
    client.conversion_goal_ids = (payload.conversion_goal_ids or "").strip() or None
    client.notes = (payload.notes or "").strip() or None
    db.commit()
    db.refresh(client)
    return _client_response(client)


@router.delete("/{client_id}")
def delete_client(
    client_id: str,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> dict[str, str]:
    db = _require_db(db)
    client = _get_owned_client(db, client_id, current)
    db.execute(delete(SyncJob).where(SyncJob.client_id == client_id))
    db.execute(delete(DirectCampaignPeriodStat).where(DirectCampaignPeriodStat.client_id == client_id))
    db.execute(delete(DirectReadCache).where(DirectReadCache.client_id == client_id))
    db.execute(delete(DirectReportJob).where(DirectReportJob.client_id == client_id))
    db.execute(delete(ClientBusinessContext).where(ClientBusinessContext.client_id == client_id))
    db.execute(delete(OptimizationActionEvent).where(OptimizationActionEvent.client_id == client_id))
    db.execute(delete(OptimizationActionDraftModel).where(OptimizationActionDraftModel.client_id == client_id))
    db.delete(client)
    db.commit()
    return {"status": "deleted", "client_id": client_id}


@router.get("/{client_id}/business-context", response_model=ClientBusinessContextResponse)
def get_client_business_context(
    client_id: str,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> ClientBusinessContextResponse:
    db = _require_db(db)
    client = _get_owned_client(db, client_id, current)
    context = _get_or_create_business_context(db, client)
    db.commit()
    db.refresh(context)
    return _business_context_response(context)


@router.put("/{client_id}/business-context", response_model=ClientBusinessContextResponse)
def update_client_business_context(
    client_id: str,
    payload: ClientBusinessContextUpdate,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> ClientBusinessContextResponse:
    db = _require_db(db)
    client = _get_owned_client(db, client_id, current)
    context = _get_or_create_business_context(db, client)
    fields_set = getattr(payload, "model_fields_set", getattr(payload, "__fields_set__", set()))
    for public_name, model_name in BUSINESS_CONTEXT_FIELD_MAP.items():
        if public_name not in fields_set:
            continue
        value = getattr(payload, public_name)
        setattr(context, model_name, value.strip() if isinstance(value, str) and value.strip() else None)
    db.commit()
    db.refresh(context)
    return _business_context_response(context)


@router.post("/{client_id}/business-context/memory-note", response_model=ClientBusinessContextResponse)
def append_client_memory_note(
    client_id: str,
    payload: ClientMemoryNoteCreate,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> ClientBusinessContextResponse:
    db = _require_db(db)
    client = _get_owned_client(db, client_id, current)
    context = _get_or_create_business_context(db, client)
    note = payload.note.strip()
    if not note:
        raise HTTPException(status_code=400, detail="Memory note is empty")
    timestamp = _now().strftime("%Y-%m-%d %H:%M")
    entry = f"[{timestamp}] {note}"
    context.memory_notes = f"{context.memory_notes.rstrip()}\n\n{entry}" if context.memory_notes else entry
    db.commit()
    db.refresh(context)
    return _business_context_response(context)


def _client_yandex_status(db: Session, client: ClientAccount, current: CurrentUser) -> ClientYandexIntegrationStatus:
    accounts = list_yandex_accounts(db, organization_id=current.organization.id)
    bound_account = next((account for account in accounts if account.id == client.yandex_account_id), None)
    return ClientYandexIntegrationStatus(
        client_id=client.id,
        connected=bound_account is not None,
        bound_account=bound_account,
        available_accounts=accounts,
        message="Yandex account is bound to this client." if bound_account else "Yandex account is not bound to this client.",
    )


@router.get("/{client_id}/integrations/yandex", response_model=ClientYandexIntegrationStatus)
def get_client_yandex_integration(
    client_id: str,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> ClientYandexIntegrationStatus:
    db = _require_db(db)
    client = _get_owned_client(db, client_id, current)
    return _client_yandex_status(db, client, current)


@router.put("/{client_id}/integrations/yandex", response_model=ClientYandexBindingStatus)
def bind_client_yandex_account(
    client_id: str,
    payload: ClientYandexBindingRequest,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> ClientYandexBindingStatus:
    db = _require_db(db)
    client = _get_owned_client(db, client_id, current)
    account = db.get(ConnectedAccount, payload.yandex_account_id)
    if not account or account.provider != "yandex" or account.organization_id != current.organization.id:
        raise HTTPException(status_code=404, detail="Yandex account not found")
    client.yandex_account_id = account.id
    db.commit()
    return ClientYandexBindingStatus(status="bound", client_id=client_id, yandex_account_id=account.id)


@router.delete("/{client_id}/integrations/yandex", response_model=ClientYandexBindingStatus)
def unbind_client_yandex_account(
    client_id: str,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> ClientYandexBindingStatus:
    db = _require_db(db)
    client = _get_owned_client(db, client_id, current)
    client.yandex_account_id = None
    db.commit()
    return ClientYandexBindingStatus(status="unbound", client_id=client_id, yandex_account_id=None)


@router.delete("/{client_id}/integrations/yandex/accounts/{account_id}", response_model=dict[str, object])
def delete_yandex_account(
    client_id: str,
    account_id: str,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> dict[str, object]:
    db = _require_db(db)
    _get_owned_client(db, client_id, current)
    account = db.get(ConnectedAccount, account_id)
    if not account or account.provider != "yandex" or account.organization_id != current.organization.id:
        raise HTTPException(status_code=404, detail="Yandex account not found")

    affected_clients = db.scalars(
        select(ClientAccount).where(
            ClientAccount.organization_id == current.organization.id,
            ClientAccount.yandex_account_id == account.id,
        )
    ).all()
    unbound_client_ids: list[str] = []
    for owned_client in affected_clients:
        owned_client.yandex_account_id = None
        unbound_client_ids.append(owned_client.id)

    db.execute(delete(OAuthToken).where(OAuthToken.account_id == account.id))
    db.delete(account)
    db.commit()
    return {
        "status": "deleted",
        "account_id": account_id,
        "unbound_clients": len(unbound_client_ids),
        "unbound_client_ids": unbound_client_ids,
    }


@router.get("/metrics", response_model=list[AgencyMetric])
def list_agency_metrics() -> list[AgencyMetric]:
    return AGENCY_METRICS


@router.get("/{client_id}", response_model=ClientSummary | ClientAccountResponse)
def get_client(
    client_id: str,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> ClientSummary | ClientAccountResponse:
    if db is not None:
        return _client_response(_get_owned_client(db, client_id, current))
    raise HTTPException(status_code=404, detail="Client not found")


@router.get("/{client_id}/campaigns", response_model=list[Campaign])
def list_client_campaigns(
    client_id: str,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> list[Campaign]:
    if db is not None:
        _get_owned_client(db, client_id, current)
        return []
    client_ids = {client.id for client in CLIENTS}
    if client_id not in client_ids:
        raise HTTPException(status_code=404, detail="Client not found")
    return CAMPAIGNS


@router.post("/{client_id}/ai/recommendations", response_model=AiRecommendationResponse)
async def create_client_ai_recommendations(
    client_id: str,
    payload: AiClientRecommendationRequest | None = None,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> AiRecommendationResponse:
    db = _require_db(db)
    _get_owned_client(db, client_id, current)
    context = build_client_ai_context_from_db(db, client_id)
    return await generate_client_recommendations_from_context(
        context=context,
        model=payload.model if payload else None,
        ai_preset=payload.ai_preset if payload else None,
        max_tokens=payload.max_tokens if payload else None,
    )


@router.get("/{client_id}/ai/context")
def get_client_ai_context(
    client_id: str,
    selected_campaign_name: str | None = None,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> dict:
    db = _require_db(db)
    _get_owned_client(db, client_id, current)
    try:
        return build_client_ai_context_from_db(db, client_id, selected_campaign_name=selected_campaign_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{client_id}/ai/prompt-debug")
def get_client_ai_prompt_debug(
    client_id: str,
    model: str | None = None,
    ai_preset: str | None = None,
    max_tokens: int | None = None,
    mode: str = "recommendations",
    selected_campaign_name: str | None = None,
    message: str | None = None,
    compact_context: bool = True,
    tool_results_mode: str = "summary",
    chat_history_limit: int = 3,
    search_query_limit: int | None = 20,
    history_json: str | None = None,
    include_preview: bool = False,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> dict:
    db = _require_db(db)
    _get_owned_client(db, client_id, current)
    context = build_client_ai_context_from_db(db, client_id, selected_campaign_name=selected_campaign_name)
    if mode == "chat":
        ai_options = normalize_ai_request_options(
            model=model,
            ai_preset=ai_preset,
            max_tokens=max_tokens,
            models=production_ai_model_ids(),
            configured_default=DEFAULT_PRODUCTION_AI_MODEL,
            production_only=True,
        )
        selected_model = str(ai_options["model"])
        compacted_context = compact_client_context_for_chat(
            context,
            compact_context=compact_context,
            search_query_limit=search_query_limit,
            selected_campaign_name=selected_campaign_name,
        )
        chat_message = message or "Проанализируй выбранного клиента DirectPilot AI."
        chat_history: list[AiChatMessage] = []
        if history_json:
            try:
                raw_history = json.loads(history_json)
                if isinstance(raw_history, list):
                    chat_history = [
                        AiChatMessage(**item)
                        for item in raw_history
                        if isinstance(item, dict) and item.get("role") and item.get("content")
                    ][-8:]
            except (TypeError, ValueError):
                chat_history = []
        return build_chat_prompt_debug_snapshot(
            client_id=client_id,
            message=chat_message,
            model=selected_model,
            history=chat_history,
            client_context=compacted_context,
            max_tokens=int(ai_options["max_tokens"]),
            include_preview=include_preview,
            display_message=message,
            compact_context=compact_context,
            tool_results_mode=tool_results_mode,
            chat_history_limit=chat_history_limit,
            search_query_limit=search_query_limit,
            selected_campaign_name=selected_campaign_name,
        )
    return build_recommendation_prompt_debug_snapshot(
        context=context,
        model=model,
        ai_preset=ai_preset,
        max_tokens=max_tokens,
        include_preview=include_preview,
    )


@router.post("/{client_id}/sync", response_model=SyncJobResponse)
def sync_client(
    client_id: str,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> SyncJobResponse:
    db = _require_db(db)
    _get_owned_client(db, client_id, current)
    job = run_client_sync(db=db, client_id=client_id)
    return _sync_job_response(job)


@router.get("/{client_id}/sync/jobs", response_model=list[SyncJobResponse])
def get_client_sync_jobs(
    client_id: str,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> list[SyncJobResponse]:
    db = _require_db(db)
    _get_owned_client(db, client_id, current)
    jobs = list_sync_jobs(db=db, client_id=client_id)
    return [_sync_job_response(item) for item in jobs]


@router.get("/{client_id}/performance-summary", response_model=ClientPerformanceSummaryResponse)
def get_client_performance_summary(
    client_id: str,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> ClientPerformanceSummaryResponse:
    db = _require_db(db)
    _get_owned_client(db, client_id, current)
    try:
        return ClientPerformanceSummaryResponse(**build_performance_summary(db=db, client_id=client_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{client_id}/optimization-plan", response_model=OptimizationPlanResponse)
def get_client_optimization_plan(
    client_id: str,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> OptimizationPlanResponse:
    db = _require_db(db)
    _get_owned_client(db, client_id, current)
    try:
        return OptimizationPlanResponse(**build_optimization_plan(db=db, client_id=client_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{client_id}/optimization-actions", response_model=OptimizationActionDraftListResponse)
def list_client_optimization_actions(
    client_id: str,
    status: str | None = None,
    source: str | None = None,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> OptimizationActionDraftListResponse:
    db = _require_db(db)
    _get_owned_client(db, client_id, current)
    query = select(OptimizationActionDraftModel).where(
        OptimizationActionDraftModel.client_id == client_id,
        OptimizationActionDraftModel.organization_id == current.organization.id,
    )
    if status:
        query = query.where(OptimizationActionDraftModel.status == status)
    if source:
        query = query.where(OptimizationActionDraftModel.source == source)
    actions = db.scalars(query.order_by(OptimizationActionDraftModel.created_at.desc())).all()
    return OptimizationActionDraftListResponse(actions=[_optimization_action_response(item) for item in actions])


def _create_action_from_payload(
    db: Session,
    *,
    client: ClientAccount,
    payload: OptimizationActionDraftCreate,
) -> OptimizationActionDraftModel:
    action = OptimizationActionDraftModel(
        organization_id=client.organization_id,
        client_id=client.id,
        source=payload.source,
        status="draft",
        severity=payload.severity,
        category=payload.category,
        campaign_name=payload.campaign_name,
        issue=payload.issue,
        evidence=payload.evidence,
        draft_action=payload.draft_action,
        action_type=payload.action_type,
        requires_approval=payload.requires_approval,
        can_apply_automatically=False,
        safety_note=payload.safety_note or "Черновик действия. Изменения в Яндекс.Директ не применялись.",
        user_comment=payload.user_comment,
    )
    db.add(action)
    db.flush()
    _append_action_event(db, action=action, event_type="created", to_status=action.status, comment=payload.user_comment)
    if payload.user_comment:
        _append_action_event(db, action=action, event_type="comment_added", comment=payload.user_comment)
    return action


@router.post("/{client_id}/optimization-actions/from-plan", response_model=OptimizationActionDraftListResponse)
def save_optimization_plan_as_actions(
    client_id: str,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> OptimizationActionDraftListResponse:
    db = _require_db(db)
    client = _get_owned_client(db, client_id, current)
    plan = build_optimization_plan(db=db, client_id=client_id)
    saved: list[OptimizationActionDraftModel] = []
    for item in plan.get("actions", []):
        existing = db.scalar(
            select(OptimizationActionDraftModel).where(
                OptimizationActionDraftModel.client_id == client_id,
                OptimizationActionDraftModel.organization_id == current.organization.id,
                OptimizationActionDraftModel.source == "rule_based",
                OptimizationActionDraftModel.campaign_name == item.get("campaign_name"),
                OptimizationActionDraftModel.issue == item.get("issue"),
                OptimizationActionDraftModel.draft_action == item.get("draft_action"),
            )
        )
        if existing:
            saved.append(existing)
            continue
        payload = OptimizationActionDraftCreate(
            source="rule_based",
            severity=item.get("severity"),
            category=item.get("category"),
            campaign_name=item.get("campaign_name"),
            issue=item.get("issue") or "Проверить кампанию",
            evidence=item.get("evidence"),
            draft_action=item.get("draft_action") or "Проверить кампанию вручную.",
            action_type=item.get("action_type") or "manual_review",
            requires_approval=bool(item.get("requires_approval", True)),
            can_apply_automatically=False,
            safety_note=item.get("safety_note") or "Черновик действия. Изменения в Яндекс.Директ не применялись.",
        )
        saved.append(_create_action_from_payload(db, client=client, payload=payload))
    db.commit()
    for action in saved:
        db.refresh(action)
    return OptimizationActionDraftListResponse(actions=[_optimization_action_response(item) for item in saved])


@router.post("/{client_id}/optimization-actions", response_model=OptimizationActionDraftResponse, status_code=status.HTTP_201_CREATED)
def create_client_optimization_action(
    client_id: str,
    payload: OptimizationActionDraftCreate,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> OptimizationActionDraftResponse:
    db = _require_db(db)
    client = _get_owned_client(db, client_id, current)
    action = _create_action_from_payload(db, client=client, payload=payload)
    db.commit()
    db.refresh(action)
    return _optimization_action_response(action)


@router.patch("/{client_id}/optimization-actions/{action_id}", response_model=OptimizationActionDraftResponse)
def update_client_optimization_action(
    client_id: str,
    action_id: str,
    payload: OptimizationActionDraftUpdateStatus,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> OptimizationActionDraftResponse:
    db = _require_db(db)
    _get_owned_client(db, client_id, current)
    action = _get_owned_action(db, client_id, action_id, current)
    old_status = action.status
    new_status = payload.status or old_status
    if new_status != old_status:
        if new_status not in ALLOWED_ACTION_TRANSITIONS.get(old_status, set()):
            raise HTTPException(status_code=400, detail=f"Status transition {old_status} -> {new_status} is not allowed")
        action.status = new_status
        now = _now()
        if new_status == "reviewed":
            action.reviewed_at = now
        if new_status == "approved":
            action.approved_at = now
        if new_status == "rejected":
            action.rejected_at = now
        _append_action_event(db, action=action, event_type="status_changed", from_status=old_status, to_status=new_status)
    comment = (payload.user_comment or "").strip()
    if comment and comment != (action.user_comment or ""):
        action.user_comment = comment
        _append_action_event(db, action=action, event_type="comment_added", comment=comment)
    db.commit()
    db.refresh(action)
    return _optimization_action_response(action)


@router.get(
    "/{client_id}/optimization-actions/{action_id}/execution-preview",
    response_model=OptimizationActionExecutionPreviewResponse,
)
def get_client_optimization_action_execution_preview(
    client_id: str,
    action_id: str,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> OptimizationActionExecutionPreviewResponse:
    db = _require_db(db)
    _get_owned_client(db, client_id, current)
    action = _get_owned_action(db, client_id, action_id, current)
    return _execution_preview_for_action(action)


@router.get("/{client_id}/optimization-actions/{action_id}/events", response_model=list[OptimizationActionEventResponse])
def list_client_optimization_action_events(
    client_id: str,
    action_id: str,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> list[OptimizationActionEventResponse]:
    db = _require_db(db)
    _get_owned_client(db, client_id, current)
    action = _get_owned_action(db, client_id, action_id, current)
    events = db.scalars(
        select(OptimizationActionEvent)
        .where(
            OptimizationActionEvent.action_id == action.id,
            OptimizationActionEvent.client_id == client_id,
            OptimizationActionEvent.organization_id == current.organization.id,
        )
        .order_by(OptimizationActionEvent.created_at.asc())
    ).all()
    return [_optimization_event_response(item) for item in events]
