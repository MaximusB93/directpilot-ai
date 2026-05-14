from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.connectors.yandex_direct import YandexDirectConnector
from app.db import get_db
from app.schemas import YandexCampaignReportRow, YandexDirectCampaign, YandexDirectConnectionCheck
from app.services.connected_accounts import get_latest_yandex_access_token

router = APIRouter(prefix="/yandex-direct", tags=["yandex-direct"])


def _float(value: str | None) -> float:
    if value in {None, "", "--"}:
        return 0.0
    return float(str(value).replace("%", "").replace(",", "."))


def _optional_float(value: str | None) -> float | None:
    if value in {None, "", "--"}:
        return None
    return _float(value)


def _int(value: str | None) -> int:
    if value in {None, "", "--"}:
        return 0
    return int(float(str(value).replace(",", ".")))


def _connector(db: Session, client_login: str | None = None) -> YandexDirectConnector:
    token = get_latest_yandex_access_token(db)
    if not token:
        raise HTTPException(status_code=404, detail="Connect a Yandex account before requesting Direct data.")
    return YandexDirectConnector(access_token=token, client_login=client_login)


@router.get("/connection", response_model=YandexDirectConnectionCheck)
def check_yandex_direct_connection(db: Session = Depends(get_db)) -> YandexDirectConnectionCheck:
    token = get_latest_yandex_access_token(db)
    return YandexDirectConnectionCheck(
        configured=bool(token),
        can_call_api=bool(token),
        message="OAuth token is available for Yandex Direct API calls." if token else "No connected Yandex OAuth token found.",
    )


@router.get("/campaigns", response_model=list[YandexDirectCampaign])
def list_yandex_direct_campaigns(
    limit: int = Query(default=10, ge=1, le=1000),
    client_login: str | None = None,
    db: Session = Depends(get_db),
) -> list[YandexDirectCampaign]:
    try:
        campaigns = _connector(db, client_login).list_campaigns(limit=limit)
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


@router.get("/reports/campaigns", response_model=list[YandexCampaignReportRow])
def get_yandex_campaign_report(
    days: int = Query(default=30, ge=1, le=366),
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = Query(default=1000, ge=1, le=10000),
    client_login: str | None = None,
    db: Session = Depends(get_db),
) -> list[YandexCampaignReportRow]:
    try:
        rows = _connector(db, client_login).get_campaign_report(
            date_from=date_from,
            date_to=date_to,
            days=days,
            limit=limit,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Yandex Direct report request failed: {exc}") from exc

    return [
        YandexCampaignReportRow(
            campaign_id=row.get("CampaignId", ""),
            campaign_name=row.get("CampaignName", ""),
            impressions=_int(row.get("Impressions")),
            clicks=_int(row.get("Clicks")),
            cost=_float(row.get("Cost")),
            ctr=_float(row.get("Ctr")),
            avg_cpc=_float(row.get("AvgCpc")),
            conversions=_float(row.get("Conversions")),
            cost_per_conversion=_optional_float(row.get("CostPerConversion")),
            conversion_rate=_optional_float(row.get("ConversionRate")),
        )
        for row in rows
    ]
