from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.connectors.yandex_direct import YandexDirectConnector
from app.db import get_db
from app.schemas import YandexCampaignReportRow, YandexDirectCampaign, YandexDirectConnectionCheck
from app.services.connected_accounts import get_latest_yandex_access_token

router = APIRouter(prefix="/yandex-direct", tags=["yandex-direct"])

ALLOWED_REPORT_RANGES = {"CUSTOM_DATE", "ALL_TIME", "LAST_365_DAYS", "LAST_90_DAYS", "LAST_30_DAYS", "LAST_14_DAYS", "LAST_7_DAYS"}


def _min_available_stats_date(today: date | None = None) -> date:
    today = today or datetime.now(UTC).date()
    return date(today.year - 3, today.month, 1)


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
    date_range: str = Query(default="CUSTOM_DATE"),
    limit: int = Query(default=1000, ge=1, le=10000),
    client_login: str | None = None,
    db: Session = Depends(get_db),
) -> list[YandexCampaignReportRow]:
    date_range = date_range.upper()
    if date_range not in ALLOWED_REPORT_RANGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported date_range '{date_range}'. Use one of: {', '.join(sorted(ALLOWED_REPORT_RANGES))}.",
        )
    if date_range != "CUSTOM_DATE" and (date_from or date_to):
        raise HTTPException(status_code=400, detail="date_from/date_to can be used only with date_range=CUSTOM_DATE.")

    min_date = _min_available_stats_date()
    if date_range == "CUSTOM_DATE" and date_from and date_from < min_date:
        raise HTTPException(
            status_code=400,
            detail=(
                "Yandex Direct statistics are available for the three years prior to the current month. "
                f"Use date_from >= {min_date.isoformat()} or date_range=ALL_TIME/LAST_365_DAYS."
            ),
        )

    try:
        rows = _connector(db, client_login).get_campaign_report(
            date_from=date_from,
            date_to=date_to,
            days=days,
            limit=limit,
            date_range_type=date_range,
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
