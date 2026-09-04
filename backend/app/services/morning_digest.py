"""Morning digest: yesterday's account, read from data already stored.

The first mode that runs without a person. Every number here is computed by
code — no language model is involved, and none should be. A model asked to write
the digest drifts straight back to general statements; the point of this module
is that the thresholds, the money and the conclusion are arithmetic, and any
later prose layer can only retell what has already been decided.

Nothing here touches Yandex Direct. The digest reads `DirectCampaignDailyStat`
rows that the sync has already collected, so it cannot fail because of an
expired token and cannot be slowed down by a report queue.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ClientAccount, DirectCampaignDailyStat, MorningDigest
from app.services.metrics_core import (
    MetricComparison,
    PeriodMetrics,
    SegmentMetrics,
    build_windows,
    compare,
    decompose_cpa,
    empty_spend,
    estimate_savings,
)

# At most five findings. A digest that fires every morning stops being read, and
# then the one that mattered is the one that gets skipped.
DIGEST_MAX_FINDINGS = 5

# A finding repeating the same (client, campaign, signal) within this many days
# is marked and yields its place to anything new.
DIGEST_REPEAT_LOOKBACK_DAYS = 7

# Everything is expressed as roubles per month so findings of different shapes
# can be compared on one scale.
DAYS_IN_MONTH = 30

STATUS_OK = "ok"
STATUS_NO_DATA = "no_data"

SIGNAL_SPEND_SPIKE = "spend_spike"
SIGNAL_SPEND_DROP = "spend_drop"
SIGNAL_CPA_GROWTH = "cpa_growth"
SIGNAL_CONVERSIONS_DROP = "conversions_drop"
SIGNAL_EMPTY_SPEND_APPEARED = "empty_spend_appeared"
SIGNAL_CTR_COLLAPSE = "ctr_collapse"
SIGNAL_CAMPAIGN_STOPPED = "campaign_stopped"

SCOPE_ACCOUNT = "account"
SCOPE_CAMPAIGN = "campaign"

LEVER_EMPTY_SPEND = "empty_spend"
LEVER_CPC = "cpc"
LEVER_CR = "cr"
LEVER_BOTH = "both"
LEVER_UNKNOWN = "unknown"

# One action per (signal, lever). Fixed text, never generated: a recommendation
# without a concrete step is exactly what this product is not allowed to emit.
ACTION_TEMPLATES: dict[tuple[str, str], str] = {
    (SIGNAL_SPEND_SPIKE, LEVER_UNKNOWN): (
        "Откройте кампанию и сверьте ставки и дневной бюджет со вчерашними: "
        "подтвердите рост как запланированный или верните прежний предел."
    ),
    (SIGNAL_SPEND_DROP, LEVER_UNKNOWN): (
        "Проверьте статус кампании, дневной бюджет и модерацию объявлений: "
        "расход упал, и это чаще всего остановка, а не экономия."
    ),
    (SIGNAL_CPA_GROWTH, LEVER_CPC): (
        "Снизьте цену клика: уменьшите ставки в самых дорогих группах "
        "или ограничьте показы на площадках с самым высоким CPC."
    ),
    (SIGNAL_CPA_GROWTH, LEVER_CR): (
        "Займитесь конверсионностью: проверьте посадочную страницу и "
        "релевантность поисковых запросов, добавьте минус-слова по нецелевым."
    ),
    (SIGNAL_CPA_GROWTH, LEVER_BOTH): (
        "Разберите кампанию с двух сторон: снизьте ставки в самых дорогих "
        "группах и проверьте посадочную страницу — вклад дали и клик, и конверсия."
    ),
    (SIGNAL_CPA_GROWTH, LEVER_UNKNOWN): (
        "Сверьте расход и конверсии кампании по дням и снизьте ставки в группах "
        "с наибольшим расходом без конверсий."
    ),
    (SIGNAL_CONVERSIONS_DROP, LEVER_UNKNOWN): (
        "Проверьте работу целей в Метрике и форму на посадочной странице: "
        "расход остался, а конверсии упали."
    ),
    (SIGNAL_EMPTY_SPEND_APPEARED, LEVER_EMPTY_SPEND): (
        "Остановите кампанию или снизьте её бюджет до выяснения: "
        "расход есть, подтверждённых конверсий нет."
    ),
    (SIGNAL_CTR_COLLAPSE, LEVER_UNKNOWN): (
        "Проверьте объявления и их показы: сверьте тексты и расширения "
        "с прошлой неделей и верните отключённые объявления в работу."
    ),
    (SIGNAL_CAMPAIGN_STOPPED, LEVER_UNKNOWN): (
        "Проверьте, почему кампания перестала показываться: статус, "
        "дневной бюджет, баланс счёта и модерацию объявлений."
    ),
}

_CONFIDENCE_ORDER = ("insufficient", "low", "medium", "high")


@dataclass(frozen=True)
class DigestFinding:
    signal: str
    scope: str
    campaign_id: str | None
    campaign_name: str | None
    lever: str
    evidence: dict[str, float | None]
    money_at_stake: float | None
    confidence: str
    confirmed_by_week: bool
    action: str
    repeated: bool = False


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def _aggregate(rows: list[DirectCampaignDailyStat], date_from: date, date_to: date) -> PeriodMetrics:
    """Sum stored daily rows into one period.

    Conversions stay `None` when no row in the window carries a known value —
    that is the "we have no conversion data" state, and it must not be reported
    as a confident zero. When some rows do carry values, the known ones are
    summed; in practice conversions are known for every row or for none, because
    they depend on whether the client has goal ids configured at all.
    """
    known_conversions = [row.goal_conversions for row in rows if row.goal_conversions is not None]
    return PeriodMetrics(
        date_from=date_from,
        date_to=date_to,
        cost=sum(row.cost or 0.0 for row in rows),
        impressions=sum(row.impressions or 0 for row in rows),
        clicks=sum(row.clicks or 0 for row in rows),
        conversions=sum(known_conversions) if known_conversions else None,
    )


def _load_rows(db: Session, client_id: str, date_from: date, date_to: date) -> list[DirectCampaignDailyStat]:
    return list(
        db.scalars(
            select(DirectCampaignDailyStat).where(
                DirectCampaignDailyStat.client_id == client_id,
                DirectCampaignDailyStat.stat_date >= date_from,
                DirectCampaignDailyStat.stat_date <= date_to,
            )
        ).all()
    )


def _rows_in(rows: list[DirectCampaignDailyStat], window: tuple[date, date]) -> list[DirectCampaignDailyStat]:
    date_from, date_to = window
    return [row for row in rows if date_from <= row.stat_date <= date_to]


def _by_campaign(rows: list[DirectCampaignDailyStat]) -> dict[str, list[DirectCampaignDailyStat]]:
    grouped: dict[str, list[DirectCampaignDailyStat]] = defaultdict(list)
    for row in rows:
        grouped[row.campaign_id].append(row)
    return grouped


def _campaign_names(rows: list[DirectCampaignDailyStat]) -> dict[str, str]:
    return {row.campaign_id: row.campaign_name for row in rows if row.campaign_name}


# ---------------------------------------------------------------------------
# Money
# ---------------------------------------------------------------------------


def _monthly(value: float | None, window_days: int) -> float | None:
    if value is None or window_days <= 0:
        return None
    return value / window_days * DAYS_IN_MONTH


def _spend_change_money(comparison: MetricComparison, window_days: int) -> float | None:
    """The changed spend itself, per month. It is the amount actually in play."""
    if comparison.cost.absolute is None:
        return None
    return _monthly(abs(comparison.cost.absolute), window_days)


def _cpa_growth_money(comparison: MetricComparison, window_days: int) -> float | None:
    """What the CPA increase costs at the current conversion volume, per month."""
    delta = comparison.cpa.absolute
    conversions = comparison.conversions.current
    if delta is None or conversions is None:
        return None
    return _monthly(delta * conversions, window_days)


def _conversions_drop_money(comparison: MetricComparison, window_days: int) -> float | None:
    """The lost conversions priced at what they used to cost, per month."""
    lost = comparison.conversions.absolute
    previous_cpa = comparison.cpa.previous
    if lost is None or previous_cpa is None:
        return None
    return _monthly(abs(lost) * previous_cpa, window_days)


def _ctr_collapse_money(comparison: MetricComparison, window_days: int) -> float | None:
    """The traffic lost to the falling click-through, priced at today's CPC."""
    lost_clicks = comparison.clicks.absolute
    cpc = comparison.cpc.current
    if lost_clicks is None or cpc is None or lost_clicks >= 0:
        return None
    return _monthly(abs(lost_clicks) * cpc, window_days)


def _stopped_campaign_money(previous: PeriodMetrics, window_days: int) -> float | None:
    """The spend that used to flow through the campaign, per month."""
    if not previous.cost:
        return None
    return _monthly(previous.cost, window_days)


# ---------------------------------------------------------------------------
# Confidence
# ---------------------------------------------------------------------------


def _downgrade(confidence: str) -> str:
    """One step down the confidence ladder, floored at `insufficient`."""
    try:
        index = _CONFIDENCE_ORDER.index(confidence)
    except ValueError:
        return "insufficient"
    return _CONFIDENCE_ORDER[max(index - 1, 0)]


def _weekly_confirms(weekly: MetricComparison, metric: str, direction: str) -> bool:
    delta = getattr(weekly, metric)
    return bool(delta.is_significant and delta.direction == direction)


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------


def _finding(
    *,
    signal: str,
    scope: str,
    campaign_id: str | None,
    campaign_name: str | None,
    lever: str,
    evidence: dict[str, float | None],
    money: float | None,
    confidence: str,
    confirmed_by_week: bool,
) -> DigestFinding:
    return DigestFinding(
        signal=signal,
        scope=scope,
        campaign_id=campaign_id,
        campaign_name=campaign_name,
        lever=lever,
        evidence=evidence,
        money_at_stake=money,
        confidence=confidence if confirmed_by_week else _downgrade(confidence),
        confirmed_by_week=confirmed_by_week,
        action=ACTION_TEMPLATES[(signal, lever)],
    )


def _metric_signals(
    *,
    daily: MetricComparison,
    weekly: MetricComparison,
    daily_current: PeriodMetrics,
    daily_previous: PeriodMetrics,
    scope: str,
    campaign_id: str | None,
    campaign_name: str | None,
    target_cpa: float | None,
    window_days: int,
) -> list[DigestFinding]:
    findings: list[DigestFinding] = []

    if daily.cost.is_significant and daily.cost.direction in {"up", "down"}:
        spike = daily.cost.direction == "up"
        findings.append(
            _finding(
                signal=SIGNAL_SPEND_SPIKE if spike else SIGNAL_SPEND_DROP,
                scope=scope,
                campaign_id=campaign_id,
                campaign_name=campaign_name,
                lever=LEVER_UNKNOWN,
                evidence={
                    "cost_current": daily.cost.current,
                    "cost_previous": daily.cost.previous,
                    "cost_absolute": daily.cost.absolute,
                    "cost_percent": daily.cost.percent,
                },
                money=_spend_change_money(daily, window_days),
                confidence=daily.cost.confidence,
                confirmed_by_week=_weekly_confirms(weekly, "cost", daily.cost.direction),
            )
        )

    cpa_exceeds_target = target_cpa is None or (
        daily.cpa.current is not None and daily.cpa.current > target_cpa
    )
    if daily.cpa.is_significant and daily.cpa.direction == "up" and cpa_exceeds_target:
        decomposition = decompose_cpa(daily_current, daily_previous)
        findings.append(
            _finding(
                signal=SIGNAL_CPA_GROWTH,
                scope=scope,
                campaign_id=campaign_id,
                campaign_name=campaign_name,
                # The decomposition splits the CPA change into a price part and a
                # conversion part without a remainder, so the dominant factor is
                # the lever to pull.
                lever=decomposition.dominant_factor,
                evidence={
                    "cpa_current": daily.cpa.current,
                    "cpa_previous": daily.cpa.previous,
                    "cpa_percent": daily.cpa.percent,
                    "target_cpa": target_cpa,
                    "cpc_contribution": decomposition.cpc_contribution,
                    "cr_contribution": decomposition.cr_contribution,
                    "conversions_current": daily.conversions.current,
                },
                money=_cpa_growth_money(daily, window_days),
                confidence=daily.cpa.confidence,
                confirmed_by_week=_weekly_confirms(weekly, "cpa", "up"),
            )
        )

    if (
        daily.conversions.is_significant
        and daily.conversions.direction == "down"
        and daily.cost.direction != "down"
    ):
        findings.append(
            _finding(
                signal=SIGNAL_CONVERSIONS_DROP,
                scope=scope,
                campaign_id=campaign_id,
                campaign_name=campaign_name,
                lever=LEVER_UNKNOWN,
                evidence={
                    "conversions_current": daily.conversions.current,
                    "conversions_previous": daily.conversions.previous,
                    "conversions_percent": daily.conversions.percent,
                    "cost_current": daily.cost.current,
                    "cost_percent": daily.cost.percent,
                },
                money=_conversions_drop_money(daily, window_days),
                confidence=daily.conversions.confidence,
                confirmed_by_week=_weekly_confirms(weekly, "conversions", "down"),
            )
        )

    if daily.ctr.is_significant and daily.ctr.direction == "down":
        findings.append(
            _finding(
                signal=SIGNAL_CTR_COLLAPSE,
                scope=scope,
                campaign_id=campaign_id,
                campaign_name=campaign_name,
                lever=LEVER_UNKNOWN,
                evidence={
                    "ctr_current": daily.ctr.current,
                    "ctr_previous": daily.ctr.previous,
                    "ctr_percent": daily.ctr.percent,
                    "clicks_current": daily.clicks.current,
                    "clicks_previous": daily.clicks.previous,
                },
                money=_ctr_collapse_money(daily, window_days),
                confidence=daily.ctr.confidence,
                confirmed_by_week=_weekly_confirms(weekly, "ctr", "down"),
            )
        )

    return findings


def _empty_spend_findings(
    *,
    current_by_campaign: dict[str, PeriodMetrics],
    previous_by_campaign: dict[str, PeriodMetrics],
    weekly_by_campaign: dict[str, PeriodMetrics],
    names: dict[str, str],
    account_current: PeriodMetrics,
    target_cpa: float | None,
) -> list[DigestFinding]:
    """Campaigns that started spending without a single confirmed conversion."""
    baseline_cr = None
    if account_current.conversions is not None and account_current.clicks:
        baseline_cr = account_current.conversions / account_current.clicks or None

    def _reliable_empty(by_campaign: dict[str, PeriodMetrics]) -> dict[str, SegmentMetrics]:
        segments = [
            SegmentMetrics(key=campaign_id, label=names.get(campaign_id, campaign_id), metrics=metrics)
            for campaign_id, metrics in by_campaign.items()
        ]
        summary = empty_spend(segments, baseline_cr=baseline_cr)
        empty_keys = {item.key for item in summary.segments if item.reliable}
        return {
            segment.key: segment for segment in segments if segment.key in empty_keys
        }

    current_empty = _reliable_empty(current_by_campaign)
    previous_empty = _reliable_empty(previous_by_campaign)
    weekly_empty = _reliable_empty(weekly_by_campaign)

    findings: list[DigestFinding] = []
    for campaign_id, segment in current_empty.items():
        if campaign_id in previous_empty:
            continue
        estimate = estimate_savings(segment, baseline_cpa=target_cpa)
        findings.append(
            _finding(
                signal=SIGNAL_EMPTY_SPEND_APPEARED,
                scope=SCOPE_CAMPAIGN,
                campaign_id=campaign_id,
                campaign_name=segment.label,
                lever=LEVER_EMPTY_SPEND,
                evidence={
                    "cost": segment.metrics.cost,
                    "clicks": float(segment.metrics.clicks),
                    "conversions": segment.metrics.conversions,
                },
                money=estimate.monthly_cost_saved,
                confidence=estimate.confidence,
                confirmed_by_week=campaign_id in weekly_empty,
            )
        )
    return findings


def _stopped_campaign_findings(
    *,
    current_by_campaign: dict[str, PeriodMetrics],
    previous_by_campaign: dict[str, PeriodMetrics],
    weekly_current_by_campaign: dict[str, PeriodMetrics],
    names: dict[str, str],
    window_days: int,
) -> list[DigestFinding]:
    """A campaign that had impressions and now has none.

    Checked outside `compare()`: this is an object disappearing, not a metric
    moving, and a comparison against zero says nothing useful about it.
    """
    findings: list[DigestFinding] = []
    for campaign_id, previous in previous_by_campaign.items():
        if not previous.impressions:
            continue
        current = current_by_campaign.get(campaign_id)
        if current is not None and current.impressions:
            continue
        weekly_current = weekly_current_by_campaign.get(campaign_id)
        findings.append(
            _finding(
                signal=SIGNAL_CAMPAIGN_STOPPED,
                scope=SCOPE_CAMPAIGN,
                campaign_id=campaign_id,
                campaign_name=names.get(campaign_id, campaign_id),
                lever=LEVER_UNKNOWN,
                evidence={
                    "impressions_previous": float(previous.impressions),
                    "impressions_current": float(current.impressions) if current else 0.0,
                    "cost_previous": previous.cost,
                },
                money=_stopped_campaign_money(previous, window_days),
                confidence="medium",
                confirmed_by_week=weekly_current is None or not weekly_current.impressions,
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Selection
# ---------------------------------------------------------------------------


def _recent_signature_set(db: Session, client_id: str, digest_date: date) -> set[tuple[str | None, str]]:
    """(campaign_id, signal) pairs already shown in the last week."""
    since = digest_date - timedelta(days=DIGEST_REPEAT_LOOKBACK_DAYS)
    previous = db.scalars(
        select(MorningDigest).where(
            MorningDigest.client_id == client_id,
            MorningDigest.digest_date >= since,
            MorningDigest.digest_date < digest_date,
        )
    ).all()
    seen: set[tuple[str | None, str]] = set()
    for digest in previous:
        for item in json.loads(digest.findings_json or "[]"):
            seen.add((item.get("campaign_id"), item.get("signal")))
    return seen


def select_findings(
    findings: list[DigestFinding], *, already_seen: set[tuple[str | None, str]]
) -> list[DigestFinding]:
    """Drop what has no price, rank by money, and let new findings go first.

    A finding without `money_at_stake` never reaches the digest: asking for
    attention without naming the amount is the habit this product is built to
    break.
    """
    priced = [finding for finding in findings if finding.money_at_stake is not None]

    marked = [
        DigestFinding(**{**asdict(finding), "repeated": (finding.campaign_id, finding.signal) in already_seen})
        for finding in priced
    ]

    def sort_key(finding: DigestFinding) -> tuple[float, int]:
        # Money first; an account-level finding wins ties against a campaign one.
        return (-(finding.money_at_stake or 0.0), 0 if finding.scope == SCOPE_ACCOUNT else 1)

    fresh = sorted([item for item in marked if not item.repeated], key=sort_key)
    repeats = sorted([item for item in marked if item.repeated], key=sort_key)

    selected = fresh[:DIGEST_MAX_FINDINGS]
    if len(selected) < DIGEST_MAX_FINDINGS:
        selected.extend(repeats[: DIGEST_MAX_FINDINGS - len(selected)])
    return selected


# ---------------------------------------------------------------------------
# Building one digest
# ---------------------------------------------------------------------------


def build_digest_findings(
    db: Session, client: ClientAccount, digest_date: date
) -> tuple[list[DigestFinding], str]:
    """Compute the findings for one client and day, plus the digest status."""
    windows = build_windows(digest_date)
    daily_current_window = windows["yesterday"]
    daily_previous_window = windows["same_weekday_prev_week"]
    weekly_current_window = windows["last7"]
    weekly_previous_window = windows["previous7"]

    rows = _load_rows(db, client.id, weekly_previous_window[0], daily_current_window[1])
    if not rows:
        return [], STATUS_NO_DATA

    names = _campaign_names(rows)
    target_cpa = float(client.target_cpa) if client.target_cpa else None

    def account_metrics(window: tuple[date, date]) -> PeriodMetrics:
        return _aggregate(_rows_in(rows, window), *window)

    def campaign_metrics(window: tuple[date, date]) -> dict[str, PeriodMetrics]:
        grouped = _by_campaign(_rows_in(rows, window))
        return {
            campaign_id: _aggregate(campaign_rows, *window)
            for campaign_id, campaign_rows in grouped.items()
        }

    account_daily_current = account_metrics(daily_current_window)
    account_daily_previous = account_metrics(daily_previous_window)
    account_weekly = compare(account_metrics(weekly_current_window), account_metrics(weekly_previous_window))
    account_daily = compare(account_daily_current, account_daily_previous)

    findings: list[DigestFinding] = _metric_signals(
        daily=account_daily,
        weekly=account_weekly,
        daily_current=account_daily_current,
        daily_previous=account_daily_previous,
        scope=SCOPE_ACCOUNT,
        campaign_id=None,
        campaign_name=None,
        target_cpa=target_cpa,
        window_days=account_daily_current.days,
    )

    current_by_campaign = campaign_metrics(daily_current_window)
    previous_by_campaign = campaign_metrics(daily_previous_window)
    weekly_current_by_campaign = campaign_metrics(weekly_current_window)
    weekly_previous_by_campaign = campaign_metrics(weekly_previous_window)

    empty_window = PeriodMetrics(
        date_from=daily_current_window[0],
        date_to=daily_current_window[1],
        cost=0.0,
        impressions=0,
        clicks=0,
        conversions=None,
    )
    for campaign_id in set(current_by_campaign) | set(previous_by_campaign):
        current = current_by_campaign.get(campaign_id, empty_window)
        previous = previous_by_campaign.get(
            campaign_id,
            PeriodMetrics(
                date_from=daily_previous_window[0],
                date_to=daily_previous_window[1],
                cost=0.0,
                impressions=0,
                clicks=0,
                conversions=None,
            ),
        )
        weekly_current = weekly_current_by_campaign.get(campaign_id)
        weekly_previous = weekly_previous_by_campaign.get(campaign_id)
        weekly = compare(
            weekly_current
            if weekly_current is not None
            else _aggregate([], *weekly_current_window),
            weekly_previous
            if weekly_previous is not None
            else _aggregate([], *weekly_previous_window),
        )
        findings.extend(
            _metric_signals(
                daily=compare(current, previous),
                weekly=weekly,
                daily_current=current,
                daily_previous=previous,
                scope=SCOPE_CAMPAIGN,
                campaign_id=campaign_id,
                campaign_name=names.get(campaign_id, campaign_id),
                target_cpa=target_cpa,
                window_days=current.days,
            )
        )

    findings.extend(
        _empty_spend_findings(
            current_by_campaign=current_by_campaign,
            previous_by_campaign=previous_by_campaign,
            weekly_by_campaign=weekly_current_by_campaign,
            names=names,
            account_current=account_daily_current,
            target_cpa=target_cpa,
        )
    )
    findings.extend(
        _stopped_campaign_findings(
            current_by_campaign=current_by_campaign,
            previous_by_campaign=previous_by_campaign,
            weekly_current_by_campaign=weekly_current_by_campaign,
            names=names,
            window_days=account_daily_current.days,
        )
    )

    already_seen = _recent_signature_set(db, client.id, digest_date)
    return select_findings(findings, already_seen=already_seen), STATUS_OK


def store_digest(
    db: Session, *, client_id: str, digest_date: date, findings: list[DigestFinding], status: str
) -> MorningDigest:
    """Write the digest for one client and day, replacing any earlier run.

    An empty digest is stored exactly like a full one: "nothing happened" is a
    result, and the record is what lets tomorrow tell a repeat from a new find.
    """
    payload = json.dumps([asdict(finding) for finding in findings], ensure_ascii=False)
    existing = db.scalar(
        select(MorningDigest).where(
            MorningDigest.client_id == client_id,
            MorningDigest.digest_date == digest_date,
        )
    )
    if existing is None:
        existing = MorningDigest(client_id=client_id, digest_date=digest_date)
        db.add(existing)
    existing.findings_json = payload
    existing.findings_count = len(findings)
    existing.status = status
    existing.created_at = datetime.now(UTC)
    db.commit()
    db.refresh(existing)
    return existing


def run_client_digest(db: Session, client_id: str, digest_date: date) -> MorningDigest:
    client = db.get(ClientAccount, client_id)
    if not client:
        raise ValueError("Client not found")
    findings, status = build_digest_findings(db, client, digest_date)
    return store_digest(
        db, client_id=client_id, digest_date=digest_date, findings=findings, status=status
    )


def digest_to_dict(digest: MorningDigest) -> dict[str, object]:
    return {
        "client_id": digest.client_id,
        "digest_date": digest.digest_date.isoformat(),
        "created_at": digest.created_at.isoformat() if digest.created_at else None,
        "status": digest.status,
        "findings_count": digest.findings_count,
        "findings": json.loads(digest.findings_json or "[]"),
    }


def default_digest_date() -> date:
    """Yesterday: the last day Direct has settled data for."""
    return datetime.now(UTC).date() - timedelta(days=1)


# ---------------------------------------------------------------------------
# Batch run
# ---------------------------------------------------------------------------

# Clients are processed one at a time and the run stops before this many seconds
# have passed. The platform kills a request that outlives its own limit, and a
# silent cut halfway through is worse than an honest partial answer: the next run
# recomputes what was already done and finishes the rest.
DIGEST_TIME_BUDGET_SECONDS = 45.0


def run_digests(
    db: Session,
    *,
    digest_date: date | None = None,
    client_id: str | None = None,
    time_budget_seconds: float = DIGEST_TIME_BUDGET_SECONDS,
    monotonic: object = None,
) -> dict[str, object]:
    """Compute digests for one client or for every client, within a time budget."""
    import time as _time

    clock = monotonic or _time.monotonic
    started_at = clock()
    target_date = digest_date or default_digest_date()

    if client_id:
        clients = [client for client in [db.get(ClientAccount, client_id)] if client is not None]
    else:
        clients = list(db.scalars(select(ClientAccount).order_by(ClientAccount.id)).all())

    processed: list[dict[str, object]] = []
    remaining = 0
    for index, client in enumerate(clients):
        # Checked before starting a client, never in the middle of one, so a
        # stored digest is always a complete digest.
        if index and clock() - started_at >= time_budget_seconds:
            remaining = len(clients) - index
            break
        digest = run_client_digest(db, client.id, target_date)
        processed.append(
            {
                "client_id": client.id,
                "status": digest.status,
                "findings_count": digest.findings_count,
            }
        )

    return {
        "digest_date": target_date.isoformat(),
        "processed_count": len(processed),
        "remaining_count": remaining,
        "complete": remaining == 0,
        "clients": processed,
    }
