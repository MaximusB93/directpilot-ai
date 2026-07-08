from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.connectors.yandex_direct import YandexDirectConnector
from app.models import ClientAccount, DirectCampaignDailyStat, DirectCampaignPeriodStat, DirectSearchQueryPeriodStat, SyncJob
from app.services.connected_accounts import get_yandex_access_token_for_account
from app.services.yandex_metrika import parse_goal_ids

NO_BOUND_ACCOUNT_MESSAGE = "Yandex account is not bound to this client. Bind a Yandex account before syncing."
NO_TOKEN_MESSAGE = "Yandex OAuth token is not connected for the bound account. Reconnect Yandex Direct before syncing real data."
NO_DATA_MESSAGE = "No Yandex Direct data for selected period"
DIRECT_GOAL_FALLBACK_MESSAGE = "Direct goal conversions unavailable for selected goals. Falling back to total Direct conversions."
SEARCH_QUERY_SYNC_WARNING = "Search query report could not be loaded. Campaign sync completed; negative keyword insights are unavailable."
DAILY_SYNC_WARNING = "Daily campaign reports could not be loaded. Campaign sync completed; daily dynamics are unavailable."


def _int(v: str | None) -> int:
    return int(float(v or 0)) if v not in {None, "", "--"} else 0


def _float(v: str | None) -> float:
    return float(v or 0) if v not in {None, "", "--"} else 0.0


def _direct_goal_conversion_value(row: dict[str, str], goal_ids: list[str]) -> float | None:
    total = 0.0
    found = False
    normalized_goal_ids = {str(item).strip() for item in goal_ids if str(item).strip()}
    for key, value in row.items():
        parts = key.split("_")
        if len(parts) < 2 or parts[0] != "Conversions":
            continue
        if parts[1] not in normalized_goal_ids:
            continue
        found = True
        total += _float(value)
    if found:
        return total
    if row.get("_TotalConversions") is not None and row.get("Conversions") not in {None, "", "--"}:
        return _float(row.get("Conversions"))
    return None


def _search_query_issue_data(
    *,
    query: str,
    cost: float,
    clicks: int,
    impressions: int,
    ctr: float,
    goal_conversions: float | None,
    total_conversions: float,
) -> tuple[list[str], str | None, str | None]:
    conversions_for_decision = goal_conversions if goal_conversions is not None else total_conversions
    flags: list[str] = []
    recommended_negative_keyword = None
    reason = None

    if impressions < 50 or clicks < 3:
        flags.append("low_data")
    if impressions >= 500 and ctr < 1.0:
        flags.append("low_relevance")
    if conversions_for_decision == 0:
        if cost >= 500:
            flags.append("costly_no_goal_conversion")
        if cost > 0 and clicks >= 10:
            flags.append("candidate_negative_keyword")
            recommended_negative_keyword = query.strip()
            reason = "Запрос получил клики/расход без конверсий по выбранной цели. Черновик минус-слова, не применяется автоматически."

    return flags, recommended_negative_keyword, reason


def _daily_campaign_issue_flags(*, cost: float, clicks: int, impressions: int, ctr: float, goal_conversions: float | None) -> list[str]:
    flags: list[str] = []
    conversions = goal_conversions if goal_conversions is not None else 0
    if impressions < 100 or clicks < 10:
        flags.append("low_data")
        return flags
    if cost > 0 and conversions == 0:
        flags.append("spend_without_conversions")
    if clicks >= 10 and conversions == 0:
        flags.append("check_queries_landing_goals")
    if ctr > 0 and ctr < 1.0:
        flags.append("low_ctr")
    if ctr >= 5.0 and conversions > 0:
        flags.append("promising_campaign")
    return flags


def _store_daily_campaign_rows(
    db: Session,
    *,
    client_id: str,
    rows: list[dict[str, str]],
    goal_ids: list[str],
    goal_ids_text: str | None,
) -> int:
    inserted = 0
    for row in rows:
        raw_date = row.get("Date") or row.get("stat_date") or row.get("StatDate")
        if not raw_date:
            continue
        try:
            stat_date = date.fromisoformat(str(raw_date)[:10])
        except ValueError:
            continue
        cost = _float(row.get("Cost"))
        clicks = _int(row.get("Clicks"))
        impressions = _int(row.get("Impressions"))
        ctr = _float(row.get("Ctr"))
        goal_conversions = _direct_goal_conversion_value(row, goal_ids) if goal_ids else None
        goal_cpa = (cost / goal_conversions) if goal_conversions else None
        conversion_rate = (goal_conversions / clicks * 100) if goal_conversions is not None and clicks else None
        flags = _daily_campaign_issue_flags(
            cost=cost,
            clicks=clicks,
            impressions=impressions,
            ctr=ctr,
            goal_conversions=goal_conversions,
        )
        db.add(
            DirectCampaignDailyStat(
                client_id=client_id,
                stat_date=stat_date,
                campaign_id=str(row.get("CampaignId") or ""),
                campaign_name=str(row.get("CampaignName") or ""),
                impressions=impressions,
                clicks=clicks,
                cost=cost,
                ctr=ctr,
                avg_cpc=_float(row.get("AvgCpc")),
                goal_ids=goal_ids_text,
                goal_conversions=goal_conversions,
                goal_cpa=goal_cpa,
                conversion_rate=conversion_rate,
                issue_flags=",".join(flags) if flags else None,
            )
        )
        inserted += 1
    return inserted


def sync_campaign_daily_stats(db: Session, client_id: str, days: int = 30) -> dict[str, object]:
    client = db.get(ClientAccount, client_id)
    if not client:
        raise ValueError("Client not found")
    if not client.yandex_account_id:
        return {"status": "skipped", "rows": 0, "warning": NO_BOUND_ACCOUNT_MESSAGE}
    token = get_yandex_access_token_for_account(db, client.yandex_account_id)
    if not token:
        return {"status": "skipped", "rows": 0, "warning": NO_TOKEN_MESSAGE}

    date_to = datetime.now(UTC).date() - timedelta(days=1)
    date_from = date_to - timedelta(days=max(days, 1) - 1)
    goal_ids = parse_goal_ids(client.conversion_goal_ids, fallback=client.main_goal_id)
    goal_ids_text = ", ".join(goal_ids) or None
    connector = YandexDirectConnector(access_token=token, client_login=client.direct_login)

    db.execute(
        delete(DirectCampaignDailyStat).where(
            DirectCampaignDailyStat.client_id == client_id,
            DirectCampaignDailyStat.stat_date >= date_from,
            DirectCampaignDailyStat.stat_date <= date_to,
        )
    )
    rows = connector.get_campaign_daily_range_report(
        date_from=date_from,
        date_to=date_to,
        goal_ids=goal_ids or None,
    )
    inserted = _store_daily_campaign_rows(
        db,
        client_id=client_id,
        rows=rows,
        goal_ids=goal_ids,
        goal_ids_text=goal_ids_text,
    )
    return {
        "status": "success",
        "rows": inserted,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
    }


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
            db.execute(delete(DirectSearchQueryPeriodStat).where(DirectSearchQueryPeriodStat.client_id == client_id))
            db.execute(delete(DirectCampaignDailyStat).where(DirectCampaignDailyStat.client_id == client_id))
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
            db.execute(delete(DirectSearchQueryPeriodStat).where(DirectSearchQueryPeriodStat.client_id == client_id))
            db.execute(delete(DirectCampaignDailyStat).where(DirectCampaignDailyStat.client_id == client_id))
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
        goal_ids = parse_goal_ids(client.conversion_goal_ids, fallback=client.main_goal_id)
        rows = connector.get_campaign_report(days=days, date_range_type="CUSTOM_DATE", goal_ids=goal_ids or None)
        goal_ids_text = ", ".join(goal_ids) or None

        db.execute(delete(DirectCampaignPeriodStat).where(DirectCampaignPeriodStat.client_id == client_id))
        db.execute(delete(DirectSearchQueryPeriodStat).where(DirectSearchQueryPeriodStat.client_id == client_id))

        matched_goal_campaigns = 0
        for row in rows:
            total_conversions = _float(row.get("_TotalConversions") or row.get("Conversions"))
            goal_conversions = None
            conversion_source = "yandex_direct_total"
            conversion_warning = None
            campaign_name = str(row.get("CampaignName") or "")
            campaign_id = str(row.get("CampaignId") or "")
            if goal_ids:
                direct_goal_conversions = _direct_goal_conversion_value(row, goal_ids)
                if direct_goal_conversions is not None:
                    matched_goal_campaigns += 1
                    goal_conversions = direct_goal_conversions
                    conversion_source = "yandex_direct_goals"
                else:
                    conversion_source = "fallback_total_when_goal_unavailable"
                    conversion_warning = DIRECT_GOAL_FALLBACK_MESSAGE
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

        search_query_warning = None
        try:
            search_rows = connector.get_search_query_report(days=days, date_range_type="CUSTOM_DATE", goal_ids=goal_ids or None)
            for row in search_rows:
                query = str(row.get("Query") or row.get("SearchQuery") or "").strip()
                if not query:
                    continue
                total_conversions = _float(row.get("_TotalConversions") or row.get("Conversions"))
                goal_conversions = None
                conversion_source = "yandex_direct_total"
                if goal_ids:
                    direct_goal_conversions = _direct_goal_conversion_value(row, goal_ids)
                    if direct_goal_conversions is not None:
                        goal_conversions = direct_goal_conversions
                        conversion_source = "yandex_direct_goals"
                    else:
                        conversion_source = "fallback_total_when_goal_unavailable"
                cost = _float(row.get("Cost"))
                clicks = _int(row.get("Clicks"))
                impressions = _int(row.get("Impressions"))
                ctr = _float(row.get("Ctr"))
                flags, negative_keyword, reason = _search_query_issue_data(
                    query=query,
                    cost=cost,
                    clicks=clicks,
                    impressions=impressions,
                    ctr=ctr,
                    goal_conversions=goal_conversions,
                    total_conversions=total_conversions,
                )
                goal_cpa = (cost / goal_conversions) if goal_conversions else None
                db.add(
                    DirectSearchQueryPeriodStat(
                        client_id=client_id,
                        campaign_id=str(row.get("CampaignId") or "") or None,
                        campaign_name=str(row.get("CampaignName") or "") or None,
                        ad_group_id=str(row.get("AdGroupId") or "") or None,
                        ad_group_name=str(row.get("AdGroupName") or "") or None,
                        query=query,
                        period_from=date_from,
                        period_to=now,
                        impressions=impressions,
                        clicks=clicks,
                        cost=cost,
                        ctr=ctr,
                        avg_cpc=_float(row.get("AvgCpc")),
                        conversions=total_conversions,
                        goal_ids=goal_ids_text,
                        goal_conversions=goal_conversions,
                        goal_cpa=goal_cpa,
                        conversion_source=conversion_source,
                        issue_flags=",".join(flags) if flags else None,
                        recommended_negative_keyword=negative_keyword,
                        recommendation_reason=reason,
                    )
                )
        except Exception as exc:
            search_query_warning = f"{SEARCH_QUERY_SYNC_WARNING} {str(exc)[:300]}"

        try:
            daily_result = sync_campaign_daily_stats(db, client_id, days=min(max(days, 30), 30))
            daily_warning = str(daily_result.get("warning")) if daily_result.get("warning") else None
        except Exception as exc:
            daily_warning = f"{DAILY_SYNC_WARNING} {str(exc)[:300]}"

        if rows:
            client.sync_status = "ok"
            if goal_ids and matched_goal_campaigns == 0:
                client.sync_error = DIRECT_GOAL_FALLBACK_MESSAGE
            else:
                client.sync_error = None
            if search_query_warning:
                client.sync_error = f"{client.sync_error}; {search_query_warning}" if client.sync_error else search_query_warning
            if daily_warning:
                client.sync_error = f"{client.sync_error}; {daily_warning}" if client.sync_error else daily_warning
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


def list_sync_jobs(db: Session, client_id: str, *, limit: int = 20) -> list[SyncJob]:
    safe_limit = max(1, min(limit, 50))
    return db.scalars(
        select(SyncJob)
        .where(SyncJob.client_id == client_id)
        .order_by(SyncJob.created_at.desc())
        .limit(safe_limit)
    ).all()
