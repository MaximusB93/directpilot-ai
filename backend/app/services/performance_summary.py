from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ClientAccount, DirectCampaignPeriodStat
from app.services.yandex_metrika import parse_goal_ids


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


def _conversion_source_message(goal_ids: list[str], has_goal_data: bool) -> str:
    if goal_ids and has_goal_data:
        return f"Используются конверсии целей Метрики: {', '.join(goal_ids)}."
    if goal_ids:
        return "Используются общие конверсии из Директа, данные по целям Метрики не получены."
    return "ID целей Метрики не указаны. Используются общие конверсии из Директа."


def _build_sync_diagnostics(
    *,
    client: ClientAccount,
    rows: list[DirectCampaignPeriodStat],
    goal_ids: list[str],
    has_goal_data: bool,
    warnings: list[str],
) -> dict:
    source_counts: dict[str, int] = {}
    for item in rows:
        source = item.conversion_source or "unknown"
        source_counts[source] = source_counts.get(source, 0) + 1

    direct_rows_loaded = len(rows)
    goal_matched = sum(1 for item in rows if item.goal_conversions is not None)
    goal_unmatched = sum(
        1
        for item in rows
        if goal_ids and (item.conversion_source or "") == "metrika_goal_unavailable"
    )
    diagnostic_warnings = list(warnings)
    if not direct_rows_loaded:
        level = "critical"
        message = "Нет сохранённых строк Яндекс.Директа. Запустите синхронизацию после привязки Яндекс-аккаунта."
    elif not goal_ids:
        level = "warning"
        message = "ID целей Метрики не указаны. CPA считается по общим конверсиям Директа."
        diagnostic_warnings.append("Укажите ID целей Метрики в настройках клиента.")
    elif not has_goal_data:
        level = "critical" if goal_unmatched else "warning"
        message = "Цели указаны, но конверсии по целям Метрики не сопоставлены с кампаниями."
        diagnostic_warnings.append("Проверьте Metrika counter, goal IDs и UTM/campaign mapping.")
    elif goal_unmatched:
        level = "warning"
        message = "Часть кампаний не получила конверсии по целям Метрики. Проверьте UTM/campaign mapping."
    else:
        level = "ok"
        message = "Данные Директа загружены, конверсии по целям сопоставлены с кампаниями."

    return {
        "clientId": client.id,
        "directRowsLoaded": direct_rows_loaded,
        "selectedGoalIds": goal_ids,
        "hasGoalIds": bool(goal_ids),
        "hasGoalData": has_goal_data,
        "goalMatchedCampaigns": goal_matched,
        "goalUnmatchedCampaigns": goal_unmatched,
        "conversionSourceCounts": source_counts,
        "warnings": sorted(set(diagnostic_warnings)),
        "dataQualityLevel": level,
        "message": message,
    }


def _severity(flags: list[str]) -> str:
    if "spend_without_conversions" in flags or "high_cpa" in flags:
        return "critical"
    if "inefficient_spend_share" in flags or "low_ctr" in flags:
        return "warning"
    if "promising_campaign" in flags:
        return "info"
    return "ok"


def _diagnostics(
    *,
    cost: float,
    clicks: int,
    impressions: int,
    ctr: float,
    conversions_used: float,
    cpa_used: float | None,
    target_cpa: int | None,
    spend_share: float,
    conversion_share: float,
) -> list[str]:
    flags: list[str] = []
    if cost > 0 and conversions_used == 0:
        flags.append("spend_without_conversions")
    if cpa_used is not None and target_cpa and cpa_used > target_cpa * 1.25:
        flags.append("high_cpa")
    if ctr > 0 and ctr < 1.0:
        flags.append("low_ctr")
    if impressions < 100 or clicks < 20:
        flags.append("low_data")
    if spend_share >= 0.25 and conversion_share < spend_share * 0.5:
        flags.append("inefficient_spend_share")
    if conversions_used > 0 and cpa_used is not None and target_cpa and cpa_used <= target_cpa:
        flags.append("promising_campaign")
    return flags


def _diagnostic_text(flags: list[str], source_message: str) -> tuple[str, str, str]:
    if "spend_without_conversions" in flags:
        return (
            "Расход без конверсий",
            f"Кампания тратит бюджет, но не даёт конверсий в выбранном источнике. {source_message}",
            "Проверить поисковые запросы, посадочную страницу, цели и ограничить неэффективные сегменты.",
        )
    if "high_cpa" in flags:
        return (
            "CPA выше целевого",
            "Стоимость конверсии заметно выше целевого CPA клиента.",
            "Проверить ставки, минус-фразы, аудитории и распределение бюджета.",
        )
    if "low_ctr" in flags:
        return ("Низкий CTR", "Объявления получают показы, но кликабельность ниже ориентира.", "Проверить тексты, быстрые ссылки и соответствие запросам.")
    if "inefficient_spend_share" in flags:
        return ("Неэффективная доля расхода", "Доля расхода выше доли конверсий.", "Сравнить с кампаниями-лидерами и перераспределить бюджет после approval.")
    if "promising_campaign" in flags:
        return ("Перспективная кампания", "Кампания даёт конверсии с CPA в пределах цели.", "Рассмотреть масштабирование после проверки качества лидов.")
    return ("Без критичных сигналов", "Явных проблем по сохранённой статистике не найдено.", "Продолжать мониторинг и накопить больше данных.")


def build_performance_summary(db: Session, client_id: str) -> dict:
    client = db.get(ClientAccount, client_id)
    if not client:
        raise ValueError("Client not found")

    rows = db.scalars(
        select(DirectCampaignPeriodStat)
        .where(DirectCampaignPeriodStat.client_id == client_id)
        .order_by(DirectCampaignPeriodStat.loaded_at.desc())
    ).all()
    goal_ids = parse_goal_ids(client.conversion_goal_ids, fallback=client.main_goal_id)
    if not rows:
        diagnostics = _build_sync_diagnostics(
            client=client,
            rows=[],
            goal_ids=goal_ids,
            has_goal_data=False,
            warnings=[],
        )
        return {
            "client": {"id": client.id, "name": client.name},
            "period": None,
            "totals": {"cost": 0.0, "impressions": 0, "clicks": 0, "conversions": 0.0, "avg_cpc": 0.0, "cpa": None},
            "campaigns": [],
            "selectedGoalId": goal_ids[0] if len(goal_ids) == 1 else None,
            "selectedGoalIds": goal_ids,
            "hasGoalData": False,
            "goalConversionsTotal": 0.0,
            "totalConversionsFallback": 0.0,
            "conversionsSourceMessage": _conversion_source_message(goal_ids, False),
            "goalDataWarnings": [],
            "syncDiagnostics": diagnostics,
            "message": "Нет сохранённых данных Яндекс.Директа. Запустите синхронизацию после подключения Яндекса.",
        }

    has_goal_data = any(item.goal_conversions is not None for item in rows)
    source_message = _conversion_source_message(goal_ids, has_goal_data)
    warnings = sorted({item.conversion_warning for item in rows if item.conversion_warning})
    sync_diagnostics = _build_sync_diagnostics(
        client=client,
        rows=rows,
        goal_ids=goal_ids,
        has_goal_data=has_goal_data,
        warnings=warnings,
    )
    period_from = min(item.period_from for item in rows)
    period_to = max(item.period_to for item in rows)
    total_cost = sum(item.cost for item in rows)
    total_conversions_used = sum((item.goal_conversions if item.goal_conversions is not None else item.conversions) for item in rows)
    totals = PerfTotals(
        cost=total_cost,
        impressions=sum(item.impressions for item in rows),
        clicks=sum(item.clicks for item in rows),
        conversions=total_conversions_used,
    )

    campaigns = []
    for item in rows:
        goal_conversions = item.goal_conversions
        conversions_used = goal_conversions if goal_conversions is not None else item.conversions
        cpa_used = item.cost / conversions_used if conversions_used else None
        spend_share = item.cost / total_cost if total_cost else 0.0
        conversion_share = conversions_used / total_conversions_used if total_conversions_used else 0.0
        flags = _diagnostics(
            cost=item.cost,
            clicks=item.clicks,
            impressions=item.impressions,
            ctr=item.ctr,
            conversions_used=conversions_used,
            cpa_used=cpa_used,
            target_cpa=client.target_cpa,
            spend_share=spend_share,
            conversion_share=conversion_share,
        )
        title, explanation, focus = _diagnostic_text(flags, source_message)
        campaigns.append(
            {
                "campaign_id": item.campaign_id,
                "campaign_name": item.campaign_name,
                "cost": item.cost,
                "impressions": item.impressions,
                "clicks": item.clicks,
                "conversions": item.conversions,
                "total_conversions": item.conversions,
                "ctr": item.ctr,
                "avg_cpc": item.avg_cpc,
                "conversion_rate": item.conversion_rate,
                "cpa": cpa_used,
                "goal_id": item.goal_id,
                "goal_ids": item.goal_ids,
                "goal_conversions": goal_conversions,
                "goal_revenue": item.goal_revenue,
                "goal_cpa": item.goal_cpa,
                "conversions_used": conversions_used,
                "conversions_used_label": "Goal conversions" if goal_conversions is not None else "Total conversions",
                "cpa_used": cpa_used,
                "conversion_source": item.conversion_source or ("yandex_direct_goal" if goal_conversions is not None else "yandex_direct_total"),
                "conversion_warning": item.conversion_warning,
                "spend_share": spend_share,
                "conversion_share": conversion_share,
                "issue_flags": flags,
                "severity": _severity(flags),
                "diagnostic_title": title,
                "diagnostic_explanation": explanation,
                "recommended_focus": focus,
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
        "selectedGoalId": goal_ids[0] if len(goal_ids) == 1 else None,
        "selectedGoalIds": goal_ids,
        "hasGoalData": has_goal_data,
        "goalConversionsTotal": sum(item.goal_conversions or 0 for item in rows),
        "totalConversionsFallback": sum(item.conversions for item in rows),
        "conversionsSourceMessage": source_message,
        "goalDataWarnings": warnings,
        "syncDiagnostics": sync_diagnostics,
        "message": "ok",
    }


def build_optimization_plan(db: Session, client_id: str) -> dict:
    summary = build_performance_summary(db, client_id)
    actions = []
    for index, campaign in enumerate(summary["campaigns"], start=1):
        flags = campaign.get("issue_flags", [])
        if not flags or campaign.get("severity") == "ok":
            continue
        issue = campaign.get("diagnostic_title") or "Проверить кампанию"
        actions.append(
            {
                "id": f"opt-{campaign.get('campaign_id') or index}",
                "severity": campaign.get("severity", "warning"),
                "category": "conversion_efficiency",
                "campaign_name": campaign.get("campaign_name"),
                "issue": issue,
                "evidence": (
                    f"Расход {campaign.get('cost')} ₽, клики {campaign.get('clicks')}, "
                    f"конверсии {campaign.get('conversions_used')} ({campaign.get('conversions_used_label')}), "
                    f"CPA {campaign.get('cpa_used') or '—'}."
                ),
                "draft_action": campaign.get("recommended_focus"),
                "action_type": "manual_review",
                "requires_approval": True,
                "can_apply_automatically": False,
                "safety_note": "Черновик действия. Изменения в Яндекс.Директ не применялись.",
            }
        )
    return {
        "client_id": client_id,
        "selected_goal_id": summary.get("selectedGoalId"),
        "has_data": bool(summary.get("campaigns")),
        "has_goal_data": bool(summary.get("hasGoalData")),
        "summary": summary.get("conversionsSourceMessage") or summary.get("message"),
        "actions": actions,
    }
