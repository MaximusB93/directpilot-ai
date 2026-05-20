from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.connectors.yandex_direct import YandexDirectConnector
from app.models import ClientAccount, DirectCampaignPeriodStat, SyncJob
from app.services.connected_accounts import get_latest_yandex_access_token

NO_TOKEN_MESSAGE = "Yandex OAuth token is not connected. Connect Yandex Direct before syncing real data."
NO_DATA_MESSAGE = "No Yandex Direct data for selected period"


def _int(v: str | None) -> int:
    return int(float(v or 0)) if v not in {None, "", "--"} else 0


def _float(v: str | None) -> float:
    return float(v or 0) if v not in {None, "", "--"} else 0.0


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
        if not token:
            db.execute(delete(DirectCampaignPeriodStat).where(DirectCampaignPeriodStat.client_id == client_id))
            client.sync_status = "no_connection"
            client.sync_error = NO_TOKEN_MESSAGE
            client.last_synced_at = now
            client.sync_version = (client.sync_version or 0) + 1

            job.source_type = "yandex_direct"
            job.status = "failed"
            job.rows_loaded = 0
            job.error = NO_TOKEN_MESSAGE
            job.period_from = date_from
            job.period_to = now
            job.finished_at = datetime.now(UTC)
            db.commit()
            db.refresh(job)
            return job

        connector = YandexDirectConnector(access_token=token, client_login=client.direct_login)
        rows = connector.get_campaign_report(days=days, date_range_type="CUSTOM_DATE")

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

        if rows:
            client.sync_status = "ok"
            client.sync_error = None
        else:
            client.sync_status = "no_data"
            client.sync_error = NO_DATA_MESSAGE

        client.last_synced_at = now
        client.sync_version = (client.sync_version or 0) + 1

        job.source_type = "yandex_direct"
        job.status = "success"
        job.rows_loaded = len(rows)
        job.error = None if rows else NO_DATA_MESSAGE
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

        job.source_type = "yandex_direct"
        job.status = "failed"
        job.rows_loaded = 0
        job.error = str(exc)[:500]
        job.period_from = date_from
        job.period_to = now
        job.finished_at = datetime.now(UTC)
        db.commit()
        db.refresh(job)
        return job


def list_sync_jobs(db: Session, client_id: str) -> list[SyncJob]:
    return db.scalars(select(SyncJob).where(SyncJob.client_id == client_id).order_by(SyncJob.created_at.desc())).all()
