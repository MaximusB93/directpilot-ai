from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.connectors.yandex_direct import YandexDirectConnector
from app.models import ClientAccount, DirectCampaignPeriodStat, SyncJob
from app.services.connected_accounts import get_latest_yandex_access_token


def _int(v: str | None) -> int:
    return int(float(v or 0)) if v not in {None, "", "--"} else 0


def _float(v: str | None) -> float:
    return float(v or 0) if v not in {None, "", "--"} else 0.0


def _demo_rows(now: datetime) -> list[dict]:
    return [
        {"CampaignId": "101", "CampaignName": "Поиск | Москва", "Impressions": "12000", "Clicks": "430", "Cost": "45200", "Ctr": "3.58", "AvgCpc": "105.12", "Conversions": "24", "CostPerConversion": "1883", "ConversionRate": "5.58"},
        {"CampaignId": "202", "CampaignName": "РСЯ | Интересы", "Impressions": "54000", "Clicks": "510", "Cost": "38900", "Ctr": "0.94", "AvgCpc": "76.27", "Conversions": "0", "CostPerConversion": "--", "ConversionRate": "0"},
    ]


def run_client_sync(db: Session, client_id: str, days: int = 30) -> SyncJob:
    client = db.get(ClientAccount, client_id)
    if not client:
        raise ValueError("Client not found")

    now = datetime.now(UTC)
    date_from = now - timedelta(days=days - 1)
    job = SyncJob(client_id=client_id, source_type="yandex_direct", status="pending")
    db.add(job)
    db.commit()
    db.refresh(job)

    job.status = "running"
    job.started_at = now
    db.commit()

    try:
        token = get_latest_yandex_access_token(db)
        rows: list[dict]
        source_type = "yandex_direct"
        if token:
            connector = YandexDirectConnector(access_token=token, client_login=client.direct_login)
            rows = connector.get_campaign_report(days=days, date_range_type="CUSTOM_DATE")
        else:
            rows = _demo_rows(now)
            source_type = "demo_yandex_direct"

        db.execute(delete(DirectCampaignPeriodStat).where(DirectCampaignPeriodStat.client_id == client_id))
        for row in rows:
            db.add(
                DirectCampaignPeriodStat(
                    client_id=client_id,
                    campaign_id=str(row.get("CampaignId") or ""),
                    campaign_name=str(row.get("CampaignName") or ""),
                    period_from=date_from,
                    period_to=now,
                    impressions=_int(row.get("Impressions")),
                    clicks=_int(row.get("Clicks")),
                    cost=_float(row.get("Cost")),
                    ctr=_float(row.get("Ctr")),
                    avg_cpc=_float(row.get("AvgCpc")),
                    conversions=_float(row.get("Conversions")),
                    cost_per_conversion=None if row.get("CostPerConversion") in {None, "", "--"} else _float(row.get("CostPerConversion")),
                    conversion_rate=None if row.get("ConversionRate") in {None, "", "--"} else _float(row.get("ConversionRate")),
                )
            )

        client.sync_status = "ok"
        client.sync_error = None
        client.last_synced_at = now
        client.sync_version = (client.sync_version or 0) + 1

        job.source_type = source_type
        job.status = "success"
        job.rows_loaded = len(rows)
        job.period_from = date_from
        job.period_to = now
        job.finished_at = datetime.now(UTC)
        db.commit()
        db.refresh(job)
        return job
    except Exception as exc:
        client.sync_status = "error"
        client.sync_error = str(exc)[:500]
        client.last_synced_at = datetime.now(UTC)
        client.sync_version = (client.sync_version or 0) + 1
        job.status = "failed"
        job.error = str(exc)[:500]
        job.finished_at = datetime.now(UTC)
        db.commit()
        db.refresh(job)
        return job


def list_sync_jobs(db: Session, client_id: str) -> list[SyncJob]:
    return db.scalars(select(SyncJob).where(SyncJob.client_id == client_id).order_by(SyncJob.created_at.desc())).all()
