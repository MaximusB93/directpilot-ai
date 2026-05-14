from fastapi import APIRouter

from app.schemas import IntegrationStatus
from app.services.mock_data import INTEGRATIONS

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationStatus])
def list_integrations() -> list[IntegrationStatus]:
    return INTEGRATIONS
