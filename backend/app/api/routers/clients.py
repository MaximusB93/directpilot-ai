from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_optional_db
from app.models import ClientAccount
from app.schemas import (
    AgencyMetric,
    AiClientRecommendationRequest,
    AiRecommendationResponse,
    Campaign,
    ClientAccountResponse,
    ClientCreateRequest,
    ClientSummary,
)
from app.services.ai_recommendations import generate_client_recommendations
from app.services.mock_data import AGENCY_METRICS, CAMPAIGNS, CLIENTS

router = APIRouter(prefix="/clients", tags=["clients"])


def _client_response(client: ClientAccount) -> ClientAccountResponse:
    return ClientAccountResponse(
        id=client.id,
        name=client.name,
        segment=client.segment,
        status=client.status,
        directLogin=client.direct_login or "Не подключен",
        metricaCounter=client.metrica_counter or "Не подключен",
    )


def _require_db(db: Session | None) -> Session:
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DATABASE_URL is required to persist clients.",
        )
    return db


@router.get("", response_model=list[ClientAccountResponse])
def list_clients(db: Session | None = Depends(get_optional_db)) -> list[ClientAccountResponse]:
    if db is None:
        return []
    clients = db.query(ClientAccount).order_by(ClientAccount.created_at.desc()).all()
    return [_client_response(client) for client in clients]


@router.post("", response_model=ClientAccountResponse, status_code=status.HTTP_201_CREATED)
def create_client(payload: ClientCreateRequest, db: Session | None = Depends(get_optional_db)) -> ClientAccountResponse:
    db = _require_db(db)
    client_id = payload.id or str(uuid4())
    existing = db.get(ClientAccount, client_id)
    if existing:
        raise HTTPException(status_code=409, detail="Client already exists")
    client = ClientAccount(
        id=client_id,
        name=payload.name.strip(),
        segment=payload.segment or "Клиент",
        direct_login=(payload.direct_login or "").strip() or None,
        metrica_counter=(payload.metrica_counter or "").strip() or None,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return _client_response(client)




@router.put("/{client_id}", response_model=ClientAccountResponse)
def update_client(client_id: str, payload: ClientCreateRequest, db: Session | None = Depends(get_optional_db)) -> ClientAccountResponse:
    db = _require_db(db)
    client = db.get(ClientAccount, client_id)
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    client.name = payload.name.strip()
    client.segment = payload.segment or client.segment
    client.direct_login = (payload.direct_login or "").strip() or None
    client.metrica_counter = (payload.metrica_counter or "").strip() or None
    db.commit()
    db.refresh(client)
    return _client_response(client)


@router.get("/metrics", response_model=list[AgencyMetric])
def list_agency_metrics() -> list[AgencyMetric]:
    return AGENCY_METRICS


@router.get("/{client_id}", response_model=ClientSummary | ClientAccountResponse)
def get_client(client_id: str, db: Session | None = Depends(get_optional_db)) -> ClientSummary | ClientAccountResponse:
    if db is not None:
        client = db.get(ClientAccount, client_id)
        if client:
            return _client_response(client)
    for client in CLIENTS:
        if client.id == client_id:
            return client
    raise HTTPException(status_code=404, detail="Client not found")


@router.get("/{client_id}/campaigns", response_model=list[Campaign])
def list_client_campaigns(client_id: str, db: Session | None = Depends(get_optional_db)) -> list[Campaign]:
    if db is not None and db.get(ClientAccount, client_id):
        return []
    client_ids = {client.id for client in CLIENTS}
    if client_id not in client_ids:
        raise HTTPException(status_code=404, detail="Client not found")
    return CAMPAIGNS


@router.post("/{client_id}/ai/recommendations", response_model=AiRecommendationResponse)
async def create_client_ai_recommendations(
    client_id: str,
    payload: AiClientRecommendationRequest | None = None,
) -> AiRecommendationResponse:
    return await generate_client_recommendations(
        client_id=client_id,
        model=payload.model if payload else None,
        client_context=payload.client_context if payload else None,
    )
