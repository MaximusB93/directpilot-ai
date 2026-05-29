from __future__ import annotations

from collections import Counter
from typing import Any

# Adapted methodology inspired by Silverov/yandex-direct-skill, MIT license.
# Only audit methodology, scoring, benchmarks, and checklist concepts are used.
# No shell scripts, API mutation logic, or Yandex Direct write actions are included.

CATEGORIES = [
    {"id": "conversions_metrika", "title": "Аналитика и цели", "weight": 25},
    {"id": "wasted_spend_negatives", "title": "Расход и минус-слова", "weight": 20},
    {"id": "account_structure", "title": "Структура аккаунта", "weight": 15},
    {"id": "keywords_quality", "title": "Качество ключей и запросов", "weight": 15},
    {"id": "ads_extensions", "title": "Объявления и расширения", "weight": 15},
    {"id": "settings_targeting", "title": "Настройки и таргетинг", "weight": 10},
]

SEVERITY_MULTIPLIERS = {
    "critical": 5.0,
    "high": 3.0,
    "medium": 1.5,
    "low": 0.5,
}

STATUS_SCORES = {
    "pass": 1.0,
    "warning": 0.5,
    "fail": 0.0,
}

STATUS_LABELS = {
    "pass": "Ок",
    "warning": "Требует внимания",
    "fail": "Проблема",
    "na": "Нужны дополнительные данные",
}

ISSUE_FLAG_LABELS = {
    "spend_without_conversions": "Расход без конверсий",
    "high_cpa": "CPA выше цели",
    "low_ctr": "Низкий CTR",
    "low_data": "Мало данных",
    "candidate_negative_keyword": "Кандидат в минус-слова",
    "costly_no_goal_conversion": "Расход без целевых конверсий",
    "low_relevance": "Низкая релевантность",
    "inefficient_spend_share": "Неэффективная доля расхода",
    "promising_campaign": "Перспективная кампания",
}


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def issue_flag_label(flag: str) -> str:
    return ISSUE_FLAG_LABELS.get(flag, flag)


def grade_for_score(score: float) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _as_number(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _campaigns(summary: dict) -> list[dict]:
    return [item for item in summary.get("campaigns", []) if isinstance(item, dict)]


def _goal_ids(summary: dict) -> list[str]:
    goal_ids = summary.get("selectedGoalIds") or []
    if isinstance(goal_ids, list):
        return [str(item).strip() for item in goal_ids if str(item).strip()]
    return [item.strip() for item in str(goal_ids).split(",") if item.strip()]


def _campaign_name_quality(campaigns: list[dict]) -> tuple[str, str]:
    if not campaigns:
        return "na", "Данные по кампаниям ещё не загружены."
    named = [item for item in campaigns if str(item.get("campaign_name") or "").strip()]
    if len(named) < len(campaigns):
        return "warning", "У части кампаний нет названия."
    names = [str(item.get("campaign_name") or "").lower() for item in campaigns]
    has_search_or_network = any(("search" in name or "поиск" in name or "rsya" in name or "рся" in name) for name in names)
    if has_search_or_network:
        return "pass", "В названиях кампаний видны базовые маркеры поиска/РСЯ."
    return "warning", "Названия есть, но канал, продукт или гео не очевидны по доступным данным."


def _check(
    *,
    category: str,
    check_id: str,
    title: str,
    status: str,
    severity: str,
    evidence: str,
    recommendation: str,
    source: str = "directpilot",
) -> dict:
    return {
        "id": check_id,
        "category": category,
        "title": title,
        "status": status,
        "statusLabel": status_label(status),
        "severity": severity,
        "evidence": evidence,
        "recommendation": recommendation,
        "source": source,
        "sourceLabel": "нужны дополнительные данные" if source == "needs_more_data" else "данные DirectPilot",
    }


def _build_checks(summary: dict) -> list[dict]:
    campaigns = _campaigns(summary)
    totals = summary.get("totals") or {}
    diagnostics = summary.get("syncDiagnostics") or {}
    search_insights = summary.get("searchQueryInsights") or {}
    goal_ids = _goal_ids(summary)
    has_goal_data = bool(summary.get("hasGoalData"))
    warnings = list(summary.get("goalDataWarnings") or []) + list(diagnostics.get("warnings") or [])
    target_cpa = _as_number((summary.get("client") or {}).get("target_cpa") or summary.get("targetCpa"), 0)
    if not target_cpa:
        target_cpa = _as_number(summary.get("target_cpa"), 0)

    total_cost = _as_number(totals.get("cost"))
    total_clicks = _as_number(totals.get("clicks"))
    total_impressions = _as_number(totals.get("impressions"))
    total_conversions = _as_number(totals.get("conversions"))
    account_ctr = (total_clicks / total_impressions * 100) if total_impressions else 0

    spend_without_conversions = [
        item for item in campaigns if "spend_without_conversions" in (item.get("issue_flags") or [])
    ]
    high_cpa = [item for item in campaigns if "high_cpa" in (item.get("issue_flags") or [])]
    low_ctr = [item for item in campaigns if "low_ctr" in (item.get("issue_flags") or [])]
    low_data = [item for item in campaigns if "low_data" in (item.get("issue_flags") or [])]
    search_candidates = int(search_insights.get("candidateNegativeKeywords") or 0)
    waste_cost = _as_number(search_insights.get("totalWasteCost"))
    source_counts = diagnostics.get("conversionSourceCounts") or {}
    fallback_used = bool(goal_ids and not has_goal_data) or bool(source_counts.get("fallback_total_when_goal_unavailable"))

    name_status, name_evidence = _campaign_name_quality(campaigns)

    checks = [
        _check(
            category="conversions_metrika",
            check_id="YD01",
            title="Счётчик Метрики указан",
            status="pass" if (summary.get("client") or {}).get("metrica_counter") else "warning",
            severity="critical",
            evidence="В настройках клиента указан счётчик Метрики." if (summary.get("client") or {}).get("metrica_counter") else "Счётчик Метрики не указан или не попал в сводку.",
            recommendation="Укажите счётчик Метрики в настройках клиента.",
        ),
        _check(
            category="conversions_metrika",
            check_id="YD02",
            title="ID целей настроены",
            status="pass" if goal_ids else "fail",
            severity="critical",
            evidence=f"Выбранные цели: {', '.join(goal_ids)}." if goal_ids else "ID выбранных целей не указаны.",
            recommendation="Укажите одну или несколько целей для анализа CPA.",
        ),
        _check(
            category="conversions_metrika",
            check_id="YD03",
            title="Конверсии по выбранным целям доступны",
            status="pass" if has_goal_data else ("fail" if goal_ids else "na"),
            severity="critical",
            evidence=summary.get("conversionsSourceMessage") or "Нет сообщения о данных по целям.",
            recommendation="Запустите синхронизацию и проверьте, что Директ возвращает конверсии по выбранным целям.",
            source="directpilot" if goal_ids else "needs_more_data",
        ),
        _check(
            category="conversions_metrika",
            check_id="YD04",
            title="Анализ не подменён общими конверсиями",
            status="fail" if fallback_used else ("pass" if has_goal_data else "na"),
            severity="high",
            evidence="Директ не вернул данные по выбранным целям." if fallback_used else "Используются конверсии по выбранным целям." if has_goal_data else "Синхронизированных конверсий пока нет.",
            recommendation="Проверьте ID целей и доступность отчёта перед выводами по CPA.",
            source="directpilot" if goal_ids else "needs_more_data",
        ),
        _check(
            category="wasted_spend_negatives",
            check_id="YD10",
            title="Кандидаты в минус-слова",
            status="fail" if search_candidates >= 5 else "warning" if search_candidates else "pass",
            severity="critical",
            evidence=f"Кандидатов в минус-слова: {search_candidates}; расход без цели: {waste_cost:.2f}.",
            recommendation="Проверьте кандидаты и сохраните безопасные черновики минус-слов. Автоматически не применять.",
        ),
        _check(
            category="wasted_spend_negatives",
            check_id="YD12",
            title="Отчёт по поисковым запросам загружен",
            status="pass" if search_insights.get("totalQueries") else "na",
            severity="critical",
            evidence=f"Загружено поисковых запросов: {search_insights.get('totalQueries') or 0}.",
            recommendation="Запустите синхронизацию, чтобы загрузить статистику поисковых запросов.",
            source="directpilot" if search_insights.get("totalQueries") else "needs_more_data",
        ),
        _check(
            category="wasted_spend_negatives",
            check_id="YD17",
            title="Расход без конверсий по целям",
            status="fail" if spend_without_conversions else "pass" if campaigns else "na",
            severity="high",
            evidence=f"Кампаний с расходом без конверсий по выбранным целям: {len(spend_without_conversions)}.",
            recommendation="Проверьте запросы, посадочные страницы, цели и распределение бюджета.",
            source="directpilot" if campaigns else "needs_more_data",
        ),
        _check(
            category="account_structure",
            check_id="YD19",
            title="Структура поиска/РСЯ видна по названиям",
            status=name_status,
            severity="medium",
            evidence=name_evidence,
            recommendation="Используйте названия кампаний, где видны канал, гео, продукт и интент.",
            source="directpilot" if campaigns else "needs_more_data",
        ),
        _check(
            category="account_structure",
            check_id="YD20",
            title="Глубина структуры аккаунта",
            status="warning" if len(campaigns) == 1 else "pass" if len(campaigns) > 1 else "na",
            severity="medium",
            evidence=f"Кампаний в сводке: {len(campaigns)}.",
            recommendation="Разделяйте кампании по продукту, гео и интенту, где это помогает управлению.",
            source="directpilot" if campaigns else "needs_more_data",
        ),
        _check(
            category="keywords_quality",
            check_id="YD34",
            title="Сигналы низкого CTR",
            status="fail" if len(low_ctr) >= 3 else "warning" if low_ctr else "pass" if campaigns else "na",
            severity="high",
            evidence=f"Кампаний с низким CTR: {len(low_ctr)}. CTR аккаунта: {account_ctr:.2f}%.",
            recommendation="Проверьте релевантность объявлений, интент запросов и расширения.",
            source="directpilot" if campaigns else "needs_more_data",
        ),
        _check(
            category="keywords_quality",
            check_id="YD30",
            title="Достаточно данных для выводов по качеству",
            status="warning" if low_data else "pass" if campaigns else "na",
            severity="medium",
            evidence=f"Кампаний с малым объёмом данных: {len(low_data)}.",
            recommendation="Накопите больше кликов/показов перед жёсткими решениями по оптимизации.",
            source="directpilot" if campaigns else "needs_more_data",
        ),
        _check(
            category="ads_extensions",
            check_id="YD39",
            title="Быстрые ссылки и расширения",
            status="na",
            severity="high",
            evidence="DirectPilot пока не загружает данные по расширениям объявлений.",
            recommendation="Проверьте быстрые ссылки, уточнения, изображения и визитку вручную в Директе.",
            source="needs_more_data",
        ),
        _check(
            category="ads_extensions",
            check_id="YD43",
            title="Качество UTM-разметки",
            status="na",
            severity="high",
            evidence="DirectPilot пока не загружает URL посадочных страниц и UTM-разметку.",
            recommendation="Проверьте UTM вручную или добавьте read-only диагностику URL позже.",
            source="needs_more_data",
        ),
        _check(
            category="settings_targeting",
            check_id="YD49",
            title="Целевой CPA как benchmark",
            status="fail" if high_cpa else "pass" if target_cpa and campaigns else "na",
            severity="high",
            evidence=f"Кампаний выше целевого CPA: {len(high_cpa)}." if target_cpa else "Целевой CPA не указан.",
            recommendation="Укажите целевой CPA и проверьте кампании с высоким CPA.",
            source="directpilot" if target_cpa and campaigns else "needs_more_data",
        ),
        _check(
            category="settings_targeting",
            check_id="YD51",
            title="Стратегии и корректировки ставок",
            status="na",
            severity="medium",
            evidence="DirectPilot пока не загружает стратегии, гео, расписание и корректировки ставок.",
            recommendation="Проверьте ограничения стратегий и настройки таргетинга вручную.",
            source="needs_more_data",
        ),
    ]
    if warnings:
        checks.append(
            _check(
                category="conversions_metrika",
                check_id="YD06",
                title="Предупреждения синхронизации разобраны",
                status="warning",
                severity="medium",
                evidence="; ".join(str(item) for item in warnings[:3]),
                recommendation="Разберите предупреждения синхронизации перед окончательными выводами по CPA.",
            )
        )
    return checks


def _score_checks(checks: list[dict], category_weight: float) -> tuple[float, float, float]:
    earned = 0.0
    possible = 0.0
    for check in checks:
        status = check.get("status")
        if status == "na":
            continue
        severity = check.get("severity") or "medium"
        multiplier = SEVERITY_MULTIPLIERS.get(severity, 1.5)
        possible += multiplier
        earned += STATUS_SCORES.get(status, 0.0) * multiplier
    if not possible:
        return 0.0, earned, possible
    return round((earned / possible) * 100, 1), earned, possible


def build_yandex_direct_audit(summary: dict) -> dict:
    checks = _build_checks(summary)
    categories = []
    weighted_score = 0.0
    total_weight = 0.0
    for category in CATEGORIES:
        category_checks = [item for item in checks if item.get("category") == category["id"]]
        score, earned, possible = _score_checks(category_checks, category["weight"])
        if possible:
            weighted_score += score * category["weight"]
            total_weight += category["weight"]
        categories.append(
            {
                "id": category["id"],
                "title": category["title"],
                "weight": category["weight"],
                "score": score,
                "grade": grade_for_score(score) if possible else "N/A",
                "checks": category_checks,
            }
        )

    score = round(weighted_score / total_weight, 1) if total_weight else 0.0
    grade = grade_for_score(score)
    failed_or_warning = [item for item in checks if item.get("status") in {"fail", "warning"}]
    critical_issues = [
        item for item in failed_or_warning if item.get("severity") in {"critical", "high"}
    ][:8]
    quick_wins = [
        item
        for item in failed_or_warning
        if item.get("severity") in {"critical", "high"}
        and item.get("id") in {"YD02", "YD03", "YD04", "YD10", "YD17", "YD34", "YD49"}
    ][:6]
    recommendations = [
        {
            "title": item["title"],
            "severity": item["severity"],
            "evidence": item["evidence"],
            "recommendation": item["recommendation"],
            "safetyNote": "Это черновая рекомендация. Изменения в Яндекс.Директ не применялись.",
        }
        for item in failed_or_warning[:10]
    ]
    limitations = [
        {
            "id": item["id"],
            "title": item["title"],
            "evidence": item["evidence"],
            "recommendation": item["recommendation"],
            "source": item.get("source", "directpilot"),
            "sourceLabel": item.get("sourceLabel"),
            "statusLabel": item.get("statusLabel"),
        }
        for item in checks
        if item.get("status") == "na" or item.get("source") == "needs_more_data"
    ][:10]
    status_counts = Counter(item.get("status") for item in checks)
    summary_text = (
        f"Оценка аудита Яндекс.Директа: {score}/100, грейд {grade}. "
        f"Проверки: Ок {status_counts.get('pass', 0)}, "
        f"требуют внимания {status_counts.get('warning', 0)}, "
        f"проблемы {status_counts.get('fail', 0)}, "
        f"нужны дополнительные данные {status_counts.get('na', 0)}."
    )
    return {
        "methodology": "Методология из 55 проверок Яндекс.Директа, адаптированная под read-only MVP данные DirectPilot.",
        "frameworkChecksTotal": 55,
        "implementedChecks": len(checks),
        "score": score,
        "grade": grade,
        "summary": summary_text,
        "categories": categories,
        "criticalIssues": critical_issues,
        "quickWins": quick_wins,
        "recommendations": recommendations,
        "limitations": limitations,
    }
