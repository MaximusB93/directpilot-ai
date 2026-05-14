from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.connectors.yandex_direct import YandexDirectConnector
from app.db import get_db
from app.schemas import YandexDirectCampaign, YandexDirectConnectionCheck
from app.services.connected_accounts import get_latest_yandex_access_token

router = APIRouter(prefix="/yandex-direct", tags=["yandex-direct"])


@router.get("/connection", response_model=YandexDirectConnectionCheck)
def check_yandex_direct_connection(db: Session = Depends(get_db)) -> YandexDirectConnectionCheck:
    token = get_latest_yandex_access_token(db)
    return YandexDirectConnectionCheck(
        configured=bool(token),
        can_call_api=bool(token),
        message="OAuth token is available for Yandex Direct API calls." if token else "No connected Yandex OAuth token found.",
    )


@router.get("/campaigns", response_model=list[YandexDirectCampaign])
def list_yandex_direct_campaigns(limit: int = 10, db: Session = Depends(get_db)) -> list[YandexDirectCampaign]:
    token = get_latest_yandex_access_token(db)
    if not token:
        raise HTTPException(status_code=404, detail="Connect a Yandex account before requesting Direct campaigns.")

    try:
        campaigns = YandexDirectConnector(access_token=token).list_campaigns(limit=limit)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Yandex Direct API request failed: {exc}") from exc

    return [
        YandexDirectCampaign(
            id=str(campaign.get("Id")),
            name=campaign.get("Name", ""),
            status=campaign.get("Status", ""),
            state=campaign.get("State"),
            type=campaign.get("Type"),
        )
        for campaign in campaigns
    ]
