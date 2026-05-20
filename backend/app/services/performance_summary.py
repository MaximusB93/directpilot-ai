from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ClientAccount, DirectCampaignPeriodStat


@dataclass
class PerfTotals:
    cost: float
    impressions: int
    clicks: int
    conversions: float

    @property
    def avg_cpc(self) -> float:
        return self.cost / self.clicks if self.clicks else 0.0

    @property
    def cpa(self) -> float | None:
        return self.cost / self.conversions if self.conversions else None


def _flags(cost: float, conversions: float, ctr: float, clicks: int, cpa: float | None) -> list[str]:
    flags: list[str] = []
    if cost >= 1000 and conversions <= 0:
        flags.append("spend_without_conversions")
    if cpa is not None and cpa > 1700:
        flags.append("high_cpa")
    if ctr > 0 and ctr < 1.0:
        flags.append("low_ctr")
    if clicks < 20:
        flags.append("low_data")
    return flags


def build_performance_summary(db: Session, client_id: str) -> dict:
    client = db.get(ClientAccount, client_id)
    if not client:
        raise ValueError("Client not found")

    rows = db.scalars(
        select(DirectCampaignPeriodStat)
        .where(DirectCampaignPeriodStat.client_id == client_id)
        .order_by(DirectCampaignPeriodStat.loaded_at.desc())
    ).all()
    if not rows:
        return {
            "client": {"id": client.id, "name": client.name},
            "period": None,
            "totals": {"cost": 0.0, "impressions": 0, "clicks": 0, "conversions": 0.0, "avg_cpc": 0.0, "cpa": None},
            "campaigns": [],
            "message": "Нет загруженной статистики. Запустите синхронизацию.",
        }

    period_from = min(item.period_from for item in rows)
    period_to = max(item.period_to for item in rows)
    totals = PerfTotals(
        cost=sum(item.cost for item in rows),
        impressions=sum(item.impressions for item in rows),
        clicks=sum(item.clicks for item in rows),
        conversions=sum(item.conversions for item in rows),
    )

    campaigns = []
    for item in rows:
        cpa = item.cost / item.conversions if item.conversions else None
        campaigns.append(
            {
                "campaign_id": item.campaign_id,
                "campaign_name": item.campaign_name,
                "cost": item.cost,
                "impressions": item.impressions,
                "clicks": item.clicks,
                "conversions": item.conversions,
                "ctr": item.ctr,
                "avg_cpc": item.avg_cpc,
                "cpa": cpa,
                "issue_flags": _flags(item.cost, item.conversions, item.ctr, item.clicks, cpa),
            }
        )

    return {
        "client": {"id": client.id, "name": client.name},
        "period": {"from": period_from.isoformat(), "to": period_to.isoformat()},
        "totals": {
            "cost": totals.cost,
            "impressions": totals.impressions,
            "clicks": totals.clicks,
            "conversions": totals.conversions,
            "avg_cpc": totals.avg_cpc,
            "cpa": totals.cpa,
        },
        "campaigns": campaigns,
        "message": "ok",
    }
