from sqlalchemy.orm import Session

from app.connectors.yandex_direct import YandexDirectConnector
from app.connectors.yandex_metrica import YandexMetricaConnector
from app.models import ClientAccount
from app.schemas import Campaign
from app.services.connected_accounts import get_latest_yandex_access_token
from app.services.mock_data import CAMPAIGNS
from app.services.performance_audit import CampaignKpi


def parse_money(value: str | None) -> float:
    if not value:
        return 0.0
    return float(value.replace("₽", "").replace(" ", "").replace(",", ".").strip() or 0)


def parse_int(value: str | None) -> int:
    if not value:
        return 0
    return int(float(value.replace(" ", "").replace(",", ".") or 0))


def parse_percent(value: str | None) -> float:
    if not value:
        return 0.0
    return float(value.replace("%", "").replace(",", ".").strip() or 0)


def campaigns_from_mock() -> list[CampaignKpi]:
    result: list[CampaignKpi] = []
    for item in CAMPAIGNS:
        result.append(
            CampaignKpi(
                name=item.name,
                spend=parse_money(item.spend),
                clicks=0,
                conversions=float(item.leads),
                ctr=0.0,
                avg_cpc=0.0,
            )
        )
    return result


def campaigns_from_direct(db: Session, client_login: str | None = None, days: int = 30) -> tuple[list[CampaignKpi], str]:
    token = get_latest_yandex_access_token(db)
    if not token:
        return campaigns_from_mock(), "mock"
    connector = YandexDirectConnector(access_token=token, client_login=client_login)
    rows = connector.get_campaign_report(days=days, limit=1000, date_range_type="CUSTOM_DATE")
    parsed: list[CampaignKpi] = []
    for row in rows:
        parsed.append(
            CampaignKpi(
                name=str(row.get("CampaignName") or ""),
                spend=float(row.get("Cost") or 0),
                clicks=int(float(row.get("Clicks") or 0)),
                conversions=float(row.get("Conversions") or 0),
                ctr=float(row.get("Ctr") or 0),
                avg_cpc=float(row.get("AvgCpc") or 0),
            )
        )
    return parsed, "real"


def metrica_goals(db: Session, counter_id: str | None) -> tuple[list[dict], str]:
    token = get_latest_yandex_access_token(db)
    if not token or not counter_id:
        return [], "mock"
    connector = YandexMetricaConnector(access_token=token)
    goals = connector.list_goals(int(counter_id))
    return goals, "real" if goals else "mock"


def get_client_login(db: Session, client_id: str) -> str | None:
    client = db.get(ClientAccount, client_id)
    return client.direct_login if client else None
