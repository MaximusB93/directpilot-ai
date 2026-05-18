from fastapi import APIRouter, HTTPException

from app.schemas import AgencyMetric, AiClientRecommendationRequest, AiRecommendationResponse, Campaign, ClientSummary
from app.services.ai_recommendations import generate_client_recommendations
from app.services.mock_data import AGENCY_METRICS, CAMPAIGNS, CLIENTS

router = APIRouter(prefix="/clients", tags=["clients"])


@router.get("", response_model=list[ClientSummary])
def list_clients() -> list[ClientSummary]:
    return CLIENTS


@router.get("/metrics", response_model=list[AgencyMetric])
def list_agency_metrics() -> list[AgencyMetric]:
    return AGENCY_METRICS


@router.get("/{client_id}", response_model=ClientSummary)
def get_client(client_id: str) -> ClientSummary:
    for client in CLIENTS:
        if client.id == client_id:
            return client
    raise HTTPException(status_code=404, detail="Client not found")


@router.get("/{client_id}/campaigns", response_model=list[Campaign])
def list_client_campaigns(client_id: str) -> list[Campaign]:
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
