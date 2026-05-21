from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_session_user
from app.db import get_optional_db
from app.models import ClientAccount, ConnectedAccount, DirectCampaignPeriodStat, SyncJob
from app.schemas import (
    AgencyMetric,
    AiClientRecommendationRequest,
    AiRecommendationResponse,
    Campaign,
    ClientAccountResponse,
    ClientCreateRequest,
    ClientYandexBindingRequest,
    ClientYandexBindingStatus,
    ClientYandexIntegrationStatus,
    ClientSummary,
    ClientPerformanceSummaryResponse,
    OptimizationPlanResponse,
    SyncJobResponse,
)
from app.services.ai_recommendations import (
    build_client_ai_context_from_db,
    generate_client_recommendations_from_context,
)
from app.services.client_sync import list_sync_jobs, run_client_sync
from app.services.connected_accounts import list_yandex_accounts
from app.services.performance_summary import build_optimization_plan, build_performance_summary
from app.services.mock_data import AGENCY_METRICS, CAMPAIGNS, CLIENTS

router = APIRouter(prefix="/clients", tags=["clients"])


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
    db.delete(client)
    db.commit()
    return {"status": "deleted", "client_id": client_id}


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
