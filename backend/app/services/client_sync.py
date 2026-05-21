from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.connectors.yandex_direct import YandexDirectConnector
from app.models import ClientAccount, DirectCampaignPeriodStat, SyncJob
from app.services.connected_accounts import get_yandex_access_token_for_account
from app.services.yandex_metrika import load_metrika_goal_conversions, parse_goal_ids

NO_BOUND_ACCOUNT_MESSAGE = "Yandex account is not bound to this client. Bind a Yandex account before syncing."
NO_TOKEN_MESSAGE = "Yandex OAuth token is not connected for the bound account. Reconnect Yandex Direct before syncing real data."
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
        if not client.yandex_account_id:
            db.execute(delete(DirectCampaignPeriodStat).where(DirectCampaignPeriodStat.client_id == client_id))
            client.sync_status = "no_connection"
            client.sync_error = NO_BOUND_ACCOUNT_MESSAGE
            client.last_synced_at = now
            client.sync_version = (client.sync_version or 0) + 1

            job.source_type = "yandex_direct"
            job.status = "failed"
            job.rows_loaded = 0
            job.error = NO_BOUND_ACCOUNT_MESSAGE
            job.period_from = date_from
            job.period_to = now
            job.finished_at = datetime.now(UTC)
            db.commit()
            db.refresh(job)
            return job

        token = get_yandex_access_token_for_account(db, client.yandex_account_id)
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
        goal_ids = parse_goal_ids(client.conversion_goal_ids, fallback=client.main_goal_id)
        goal_ids_text = ", ".join(goal_ids) or None
        metrika = load_metrika_goal_conversions(
            access_token=token,
            counter_id=client.metrica_counter,
            goal_ids=goal_ids,
            date_from=date_from.date(),
            date_to=now.date(),
        ) if goal_ids else None
        metrika_by_campaign: dict[str, float] = {}
        if metrika:
            for item in metrika.rows:
                metrika_by_campaign[item.campaign_key.lower()] = metrika_by_campaign.get(item.campaign_key.lower(), 0.0) + item.goal_conversions
        metrika_warning = "; ".join(metrika.warnings) if metrika and metrika.warnings else None

        db.execute(delete(DirectCampaignPeriodStat).where(DirectCampaignPeriodStat.client_id == client_id))

        for row in rows:
            total_conversions = _float(row.get("Conversions"))
            goal_conversions = None
            conversion_source = "yandex_direct_total"
            conversion_warning = None
            campaign_name = str(row.get("CampaignName") or "")
            campaign_id = str(row.get("CampaignId") or "")
            if goal_ids:
                matched = metrika_by_campaign.get(campaign_name.lower()) or metrika_by_campaign.get(campaign_id.lower())
                if matched is not None:
                    goal_conversions = matched
                    conversion_source = "metrika_goals" if len(goal_ids) > 1 else "metrika_goal"
                else:
                    conversion_source = "metrika_goal_unavailable"
                    conversion_warning = metrika_warning or "Metrika goal data could not be matched to this Direct campaign."
            goal_cpa = (_float(row.get("Cost")) / goal_conversions) if goal_conversions else None
            db.add(
                DirectCampaignPeriodStat(
                    client_id=client_id,
                    campaign_id=campaign_id,
                    campaign_name=campaign_name,
                    period_from=date_from,
                    period_to=now,
                    impressions=_int(row.get("Impressions")),
                    clicks=_int(row.get("Clicks")),
                    cost=_float(row.get("Cost")),
                    ctr=_float(row.get("Ctr")),
                    avg_cpc=_float(row.get("AvgCpc")),
                    conversions=total_conversions,
                    cost_per_conversion=None if row.get("CostPerConversion") in {None, "", "--"} else _float(row.get("CostPerConversion")),
                    conversion_rate=None if row.get("ConversionRate") in {None, "", "--"} else _float(row.get("ConversionRate")),
                    goal_id=goal_ids[0] if len(goal_ids) == 1 else None,
                    goal_ids=goal_ids_text,
                    goal_conversions=goal_conversions,
                    goal_revenue=None,
                    goal_cpa=goal_cpa,
                    conversion_source=conversion_source,
                    conversion_warning=conversion_warning,
                )
            )

        if rows:
            client.sync_status = "ok"
            client.sync_error = metrika_warning if goal_ids and metrika_warning else None
        else:
            client.sync_status = "no_data"
            client.sync_error = NO_DATA_MESSAGE

        client.last_synced_at = now
        client.sync_version = (client.sync_version or 0) + 1

        job.source_type = "yandex_direct"
        job.status = "success"
        job.rows_loaded = len(rows)
        job.error = client.sync_error if rows and client.sync_error else (None if rows else NO_DATA_MESSAGE)
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
