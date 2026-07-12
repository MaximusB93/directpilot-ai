import copy
import json
import re
from datetime import UTC, date, datetime
from time import perf_counter
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_session_user
from app.connectors.yandex_direct import YandexDirectConnector
from app.core.config import (
    AI_MODEL_PRESETS,
    AI_RECOMMENDED_DEFAULT_PRESET,
    DEFAULT_PRODUCTION_AI_MODEL,
    ai_model_cost_tier,
    ai_model_label,
    ai_model_recommended_for,
    normalize_ai_request_options,
    production_ai_model_ids,
    settings,
)
from app.db import get_db, get_optional_db
from app.models import ClientAccount
from app.schemas import (
    AiAuditAdvanceRequest,
    AiAuditCreateRequest,
    AiAuditJobResponse,
    AiChatRequest,
    AiChatResponse,
    AiPromptRequest,
    AiPromptResponse,
    AiStatusResponse,
)
from app.services.ai_audit_jobs import (
    advance_audit_job,
    audit_job_response,
    cancel_audit_job,
    create_audit_job,
    get_audit_job,
    requires_staged_audit,
)
from app.services.ai_chat import answer_ai_chat, compact_client_context_for_chat, detect_analysis_intent
from app.services.ai_recommendations import build_client_ai_context_from_db
from app.services.ai_prompt_debug import build_openrouter_request_debug
from app.services.connected_accounts import get_yandex_access_token_for_account
from app.services.openrouter import DEFAULT_SYSTEM_PROMPT, generate_openrouter_response, openrouter_status
from app.services.yandex_metrika import parse_goal_ids

router = APIRouter(prefix="/ai", tags=["ai"])

AI_RATE_LIMIT_MESSAGE = "Выбранная AI-модель временно перегружена или ограничена по лимитам. Выберите другую модель или повторите позже."
MONTHS_RU = {
    "января": 1,
    "январь": 1,
    "февраля": 2,
    "февраль": 2,
    "марта": 3,
    "март": 3,
    "апреля": 4,
    "апрель": 4,
    "мая": 5,
    "май": 5,
    "июня": 6,
    "июнь": 6,
    "июля": 7,
    "июль": 7,
    "августа": 8,
    "август": 8,
    "сентября": 9,
    "сентябрь": 9,
    "октября": 10,
    "октябрь": 10,
    "ноября": 11,
    "ноябрь": 11,
    "декабря": 12,
    "декабрь": 12,
}


def _provider_from_model(model_id: str) -> str:
    return model_id.split("/", 1)[0] if "/" in model_id else "custom"


def _ai_status_payload() -> dict[str, object]:
    status = openrouter_status()
    models = []
    for item in status.get("models", []):
        model_id = str(item.get("id", ""))
        models.append(
            {
                **item,
                "label": ai_model_label(model_id),
                "provider": _provider_from_model(model_id),
                "cost_tier": ai_model_cost_tier(model_id),
                "recommended_for": ai_model_recommended_for(model_id),
            }
        )
    recommended_model = DEFAULT_PRODUCTION_AI_MODEL
    presets = [
        {
            **preset,
            "default_model": {
                "economy": "mistralai/mistral-small-3.2-24b-instruct",
                "balanced": DEFAULT_PRODUCTION_AI_MODEL,
                "advanced": "deepseek/deepseek-chat-v3.1",
            }.get(preset_id, recommended_model),
        }
        for preset_id, preset in AI_MODEL_PRESETS.items()
    ]
    return {
        **status,
        "default_model": recommended_model,
        "models": models,
        "presets": presets,
        "recommended_default_preset": AI_RECOMMENDED_DEFAULT_PRESET,
        "recommended_default_model": recommended_model,
    }


def _resolved_ai_options(model: str | None, ai_preset: str | None, max_tokens: int | None) -> dict[str, object]:
    return normalize_ai_request_options(
        model=model,
        ai_preset=ai_preset,
        max_tokens=max_tokens,
        models=production_ai_model_ids(),
        configured_default=DEFAULT_PRODUCTION_AI_MODEL,
        production_only=True,
    )


def _apply_intent_token_floor(ai_options: dict[str, object], *, message: str, explicit_max_tokens: bool) -> dict[str, object]:
    if explicit_max_tokens:
        return ai_options
    intent = detect_analysis_intent(message).get("intent")
    floors = {
        "campaign_dynamics_analysis": 2500,
        "global_direct_audit": 3000,
        "search_queries_analysis": 2000,
    }
    floor = floors.get(str(intent))
    if not floor:
        return ai_options
    current = int(ai_options["max_tokens"])
    cap = int(ai_options.get("max_tokens_cap") or current)
    return {**ai_options, "max_tokens": min(max(current, floor), cap)}


def _apply_specific_date_token_floor(ai_options: dict[str, object], *, explicit_max_tokens: bool, requested_date: date | None) -> dict[str, object]:
    if requested_date is None:
        return ai_options
    current = int(ai_options["max_tokens"])
    if explicit_max_tokens and current > 900:
        return ai_options
    cap = int(ai_options.get("max_tokens_cap") or current)
    return {**ai_options, "max_tokens": min(max(current, 2500), cap)}


def _single_day_analysis_plan(requested_date: date) -> dict[str, Any]:
    return {
        "intent": "single_day_campaign_analysis",
        "scope": "whole_account",
        "requiresCascade": True,
        "requestedPeriod": {"type": "single_date", "date": requested_date.isoformat()},
        "dataNeeds": [
            "yandex_direct_campaign_daily_report",
            "selected_goals",
            "campaigns",
            "campaign_issue_flags",
            "drilldown_plan",
        ],
        "notes": [
            "Specific date was parsed by DirectPilot router before AI prompt assembly.",
            "Use read-only Yandex Direct daily campaign report as the primary source.",
        ],
    }


def _single_day_prompt_message(user_message: str, requested_date: date) -> str:
    return f"""{user_message}

DirectPilot internal routing:
intent = single_day_campaign_analysis
requested_date = {requested_date.isoformat()}

Single-day answer rules:
- Use only the selected date from trusted context. Do not call this last7, last14 or last30.
- Start with account totals for the selected date, then split campaigns into critical, low-data and opportunity groups.
- If account CPA is above target CPA, call it high CPA. Do not call it low CPA.
- For Search campaigns, next drill-down is semantic/query report, keywords, goals and landing alignment.
- For RSYA, retargeting and content campaigns, next drill-down is placements, audiences, retargeting segments, creatives/ads, devices, geo and goals. Do not present semantic/query report as the primary check for RSYA.
- Do not recommend budget scaling from one day only. Say that 7/14/30-day stability and lead quality must be checked first.
- Keep the answer compact: facts, campaign groups, hypotheses, next checks, limitations.
- All actions are dry-run/manual approval only."""


def _decorate_specific_date_response_trace(
    response: AiChatResponse,
    *,
    requested_date: date | None,
    analysis: dict[str, Any] | None,
    original_message: str | None = None,
) -> AiChatResponse:
    if requested_date is None or not response.requestTrace:
        return response
    trace = dict(response.requestTrace)
    plan = _single_day_analysis_plan(requested_date)
    live_rows = int((analysis or {}).get("rows") or 0)
    trace["userMessage"] = original_message or trace.get("userMessage")
    trace["analysisPlan"] = plan
    trace["singleDayDirectAnalysis"] = {
        "available": bool((analysis or {}).get("available")),
        "source": (analysis or {}).get("source") or "yandex_direct_read_only_daily_report",
        "requestedDate": requested_date.isoformat(),
        "rows": live_rows,
        "status": (analysis or {}).get("status"),
        "missingData": (analysis or {}).get("missingData") or [],
    }
    trace["dataFetch"] = [
        {
            "source": "yandex_direct_live_campaign_daily_report",
            "status": "used" if live_rows else ((analysis or {}).get("status") or "missing"),
            "date": requested_date.isoformat(),
            "rows": live_rows,
            "message": "Fetched read-only from Yandex Direct during AI chat for a specific date.",
        },
        *[item for item in trace.get("dataFetch", []) if item.get("source") != "yandex_direct_live_campaign_daily_report"],
    ]
    if isinstance(trace.get("modelSettings"), dict):
        trace["modelSettings"] = {**trace["modelSettings"], "max_tokens": max(int(trace["modelSettings"].get("max_tokens") or 0), 2500)}
    if isinstance(trace.get("prompt"), dict):
        trace["prompt"] = {
            **trace["prompt"],
            "singleDayInstruction": "Answer account -> campaigns -> issues -> drill-down -> safe actions. Treat selectedDate as one day only. Do not recommend scaling from one day.",
        }
    return response.model_copy(update={"requestTrace": trace})


def _int(value: str | None) -> int:
    return int(float(value or 0)) if value not in {None, "", "--"} else 0


def _float(value: str | None) -> float:
    return float(value or 0) if value not in {None, "", "--"} else 0.0


def _round(value: float | None, digits: int = 2) -> float | None:
    return round(value, digits) if value is not None else None


def _parse_specific_date_request(message: str, *, today: date | None = None) -> date | None:
    text = (message or "").lower().replace("ё", "е")
    reference = today or datetime.now(UTC).date()

    iso_match = re.search(r"\b(20\d{2})-(\d{1,2})-(\d{1,2})\b", text)
    if iso_match:
        year, month, day = (int(part) for part in iso_match.groups())
        try:
            return date(year, month, day)
        except ValueError:
            return None

    numeric_match = re.search(r"\b(\d{1,2})[./](\d{1,2})(?:[./](20\d{2}))?\b", text)
    if numeric_match:
        day = int(numeric_match.group(1))
        month = int(numeric_match.group(2))
        year = int(numeric_match.group(3) or reference.year)
        try:
            candidate = date(year, month, day)
        except ValueError:
            return None
        if numeric_match.group(3) is None and candidate > reference:
            candidate = date(year - 1, month, day)
        return candidate

    month_pattern = "|".join(sorted(MONTHS_RU, key=len, reverse=True))
    word_match = re.search(rf"\b(\d{{1,2}})\s+({month_pattern})(?:\s+(20\d{{2}}))?\b", text)
    if not word_match:
        return None
    day = int(word_match.group(1))
    month = MONTHS_RU[word_match.group(2)]
    year = int(word_match.group(3) or reference.year)
    try:
        candidate = date(year, month, day)
    except ValueError:
        return None
    if word_match.group(3) is None and candidate > reference:
        candidate = date(year - 1, month, day)
    return candidate


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


def _campaign_issue_flags(*, cost: float, impressions: int, clicks: int, ctr: float, goal_conversions: float | None, goal_cpa: float | None, target_cpa: int | None) -> list[str]:
    conversions = goal_conversions if goal_conversions is not None else 0
    flags: list[str] = []
    if impressions < 100 or clicks < 10:
        flags.append("low_data")
    if cost > 0 and conversions == 0 and clicks >= 10:
        flags.append("spend_without_conversions")
    if target_cpa and goal_cpa is not None and goal_cpa > target_cpa * 1.25:
        flags.append("high_cpa")
    if impressions >= 500 and ctr < 1.0:
        flags.append("low_ctr")
    if conversions > 0 and target_cpa and goal_cpa is not None and goal_cpa <= target_cpa:
        flags.append("promising_campaign")
    return flags or ["ok"]


def _severity(flags: list[str]) -> str:
    if any(item in flags for item in ["spend_without_conversions", "high_cpa"]):
        return "critical"
    if "low_ctr" in flags:
        return "warning"
    if "promising_campaign" in flags:
        return "opportunity"
    if "low_data" in flags:
        return "info"
    return "ok"


def _recommended_focus(flags: list[str], campaign_name: str | None = None) -> str:
    name = (campaign_name or "").lower()
    is_network = any(token in name for token in ["рся", "ретаргет", "интерес", "товарная", "мк"])
    if "spend_without_conversions" in flags:
        if is_network:
            return "Проверить площадки, аудитории/сегменты, креативы, устройства, гео и цели. Изменения только через dry-run/approval."
        return "Проверить семантику, ключевые фразы, цели, посадочную страницу и стратегию. Изменения только через dry-run/approval."
    if "high_cpa" in flags:
        return "Проверить источники трафика, группы, ставки, цели и посадочную. Подготовить только черновики действий."
    if "low_ctr" in flags:
        if is_network:
            return "Проверить креативы, аудитории, площадки, устройства и частоту показов."
        return "Проверить релевантность объявлений, ключевые фразы и интент пользователей."
    if "promising_campaign" in flags:
        return "Проверить качество лидов и стабильность CPA за 7/14/30 дней перед масштабированием."
    if "low_data" in flags:
        return "Данных мало: не делать жёстких выводов, проверить больший период или детализацию."
    return "Существенных проблем по дневным метрикам не выявлено."


def _drilldown_next_level(flags: list[str], campaign_name: str | None = None) -> list[str]:
    name = (campaign_name or "").lower()
    is_network = any(token in name for token in ["рся", "ретаргет", "интерес", "товарная", "мк"])
    if "spend_without_conversions" in flags:
        return ["placements", "audiences", "creatives", "devices", "geo", "goals"] if is_network else ["query_report", "keywords", "goals", "landing", "strategy"]
    if "high_cpa" in flags:
        return ["placements", "audiences", "ad_groups", "goals", "landing"] if is_network else ["query_report", "ad_groups", "goals", "landing"]
    if "low_ctr" in flags:
        return ["creatives", "audiences", "placements", "devices"] if is_network else ["ads", "keywords", "query_report"]
    if "promising_campaign" in flags:
        return ["lead_quality", "7_14_30_day_stability", "budget_dry_run"]
    return ["campaign"]


def _specific_date_totals(campaigns: list[dict[str, Any]]) -> dict[str, Any]:
    cost = sum(float(item.get("cost") or 0) for item in campaigns)
    impressions = sum(int(item.get("impressions") or 0) for item in campaigns)
    clicks = sum(int(item.get("clicks") or 0) for item in campaigns)
    goal_conversions = sum(float(item.get("goal_conversions") or 0) for item in campaigns)
    return {
        "cost": _round(cost),
        "impressions": impressions,
        "clicks": clicks,
        "ctr": _round(clicks / impressions * 100) if impressions else 0.0,
        "avgCpc": _round(cost / clicks) if clicks else 0.0,
        "goalCpa": _round(cost / goal_conversions) if goal_conversions else None,
        "cpa": _round(cost / goal_conversions) if goal_conversions else None,
    }


def _build_specific_date_analysis(client: ClientAccount, requested_date: date, rows: list[dict[str, str]], goal_ids: list[str]) -> dict[str, Any]:
    campaigns: list[dict[str, Any]] = []
    goal_ids_text = ", ".join(goal_ids) or None
    for row in rows:
        cost = _float(row.get("Cost"))
        impressions = _int(row.get("Impressions"))
        clicks = _int(row.get("Clicks"))
        ctr = _float(row.get("Ctr"))
        avg_cpc = _float(row.get("AvgCpc"))
        goal_conversions = _direct_goal_conversion_value(row, goal_ids) if goal_ids else _float(row.get("Conversions"))
        goal_cpa = (cost / goal_conversions) if goal_conversions else None
        campaign_name = str(row.get("CampaignName") or "")
        flags = _campaign_issue_flags(
            cost=cost,
            impressions=impressions,
            clicks=clicks,
            ctr=ctr,
            goal_conversions=goal_conversions,
            goal_cpa=goal_cpa,
            target_cpa=client.target_cpa,
        )
        campaigns.append(
            {
                "campaign_id": str(row.get("CampaignId") or ""),
                "campaign_name": campaign_name,
                "period_date": requested_date.isoformat(),
                "cost": _round(cost),
                "impressions": impressions,
                "clicks": clicks,
                "ctr": _round(ctr),
                "avg_cpc": _round(avg_cpc),
                "goal_ids": goal_ids_text,
                "goal_conversions": _round(goal_conversions),
                "goal_cpa": _round(goal_cpa),
                "conversion_rate": _round(goal_conversions / clicks * 100) if goal_conversions is not None and clicks else None,
                "severity": _severity(flags),
                "issue_flags": flags,
                "diagnostic_explanation": f"Данные Яндекс.Директа за {requested_date.isoformat()}: расход {_round(cost)} ₽, клики {clicks}, конверсии по выбранным целям {_round(goal_conversions)}, CPA {_round(goal_cpa)}.",
                "recommended_focus": _recommended_focus(flags, campaign_name),
                "drilldown_next_level": _drilldown_next_level(flags, campaign_name),
            }
        )
    severity_rank = {"critical": 0, "warning": 1, "info": 2, "opportunity": 3, "ok": 4}
    campaigns = sorted(campaigns, key=lambda item: (severity_rank.get(item["severity"], 9), -(item.get("cost") or 0)))
    totals = _specific_date_totals(campaigns)
    goal_conversions_total = _round(sum(float(item.get("goal_conversions") or 0) for item in campaigns))
    missing_data = [] if campaigns else ["Yandex Direct returned no campaign rows for requested date."]
    return {
        "available": bool(campaigns),
        "status": "used" if campaigns else "no_data",
        "source": "yandex_direct_read_only_daily_report",
        "requestedDate": requested_date.isoformat(),
        "rows": len(campaigns),
        "accountTotals": {**totals, "goalConversions": goal_conversions_total},
        "campaigns": campaigns,
        "dataQuality": {
            "period": {"from": requested_date.isoformat(), "to": requested_date.isoformat(), "source": "live_yandex_direct_daily_report"},
            "selectedGoalIds": goal_ids,
            "hasGoalData": any(item.get("goal_conversions") is not None for item in campaigns),
            "goalConversionsTotal": goal_conversions_total,
            "message": f"Данные подтянуты read-only из Яндекс.Директа за {requested_date.isoformat()} по выбранным целям: {goal_ids_text or 'цели не выбраны'}.",
        },
        "drilldownPlan": [
            {
                "campaignName": item["campaign_name"],
                "issueFlags": item["issue_flags"],
                "nextLevel": item["drilldown_next_level"],
                "safeActions": ["manual_review", "dry_run_only"],
                "why": item["diagnostic_explanation"],
            }
            for item in campaigns[:8]
            if item["severity"] in {"critical", "warning", "info", "opportunity"}
        ],
        "mainFindings": [
            f"{item['campaign_name']}: {', '.join(item['issue_flags'])}; расход {item['cost']} ₽, клики {item['clicks']}, конверсии по целям {item['goal_conversions']}."
            for item in campaigns[:6]
        ],
        "missingData": missing_data,
        "safety": {"readOnly": True, "canApplyAutomatically": False, "message": "Данные только прочитаны из Яндекс.Директа; изменения не применялись."},
    }


def _fetch_specific_date_analysis(db: Session, client: ClientAccount, requested_date: date) -> dict[str, Any]:
    if not client.yandex_account_id:
        return {"available": False, "status": "no_yandex_account", "requestedDate": requested_date.isoformat(), "missingData": ["Yandex account is not bound to this client."]}
    token = get_yandex_access_token_for_account(db, client.yandex_account_id)
    if not token:
        return {"available": False, "status": "no_yandex_token", "requestedDate": requested_date.isoformat(), "missingData": ["Yandex account token is not connected for the bound account."]}
    goal_ids = parse_goal_ids(client.conversion_goal_ids, fallback=client.main_goal_id)
    connector = YandexDirectConnector(access_token=token, client_login=client.direct_login)
    try:
        rows = connector.get_campaign_daily_report(stat_date=requested_date, goal_ids=goal_ids or None)
    except Exception as exc:
        return {
            "available": False,
            "status": "fetch_error",
            "source": "yandex_direct_read_only_daily_report",
            "requestedDate": requested_date.isoformat(),
            "missingData": [f"Read-only Yandex Direct daily report failed: {str(exc)[:300]}"],
            "safety": {"readOnly": True, "canApplyAutomatically": False},
        }
    return _build_specific_date_analysis(client, requested_date, rows, goal_ids)


def _apply_specific_date_analysis_to_context(context: dict[str, Any] | None, analysis: dict[str, Any]) -> dict[str, Any]:
    next_context = copy.deepcopy(context or {})
    next_context["specific_date_analysis"] = analysis
    requested_date = str(analysis.get("requestedDate") or "")
    warnings = list(next_context.get("warnings") or [])
    warnings.append(f"AI chat used read-only Yandex Direct daily report for {requested_date}.")
    next_context["warnings"] = warnings
    try:
        next_context["forced_analysis_plan"] = _single_day_analysis_plan(date.fromisoformat(requested_date))
    except ValueError:
        next_context["forced_analysis_plan"] = None

    if not analysis.get("available"):
        return next_context

    summary = copy.deepcopy(next_context.get("summary") if isinstance(next_context.get("summary"), dict) else {})
    summary["period"] = analysis["dataQuality"]["period"]
    summary["totals"] = analysis["accountTotals"]
    summary["campaigns"] = analysis["campaigns"]
    summary["selectedGoalIds"] = analysis["dataQuality"].get("selectedGoalIds") or []
    summary["hasGoalData"] = analysis["dataQuality"].get("hasGoalData", False)
    summary["goalConversionsTotal"] = analysis["dataQuality"].get("goalConversionsTotal")
    summary["conversionsSourceMessage"] = analysis["dataQuality"].get("message")
    summary["searchQueryInsights"] = {}
    summary["yandexDirectAudit"] = {}

    next_context["summary"] = summary
    next_context["campaigns"] = analysis["campaigns"]
    next_context["diagnostics"] = [
        {
            "campaign_name": item.get("campaign_name"),
            "severity": item.get("severity"),
            "flags": item.get("issue_flags"),
            "explanation": item.get("diagnostic_explanation"),
            "recommended_focus": item.get("recommended_focus"),
            "next_level": item.get("drilldown_next_level"),
        }
        for item in analysis["campaigns"]
    ]
    next_context["search_query_insights"] = {}
    next_context["yandex_direct_audit"] = {}
    next_context["optimization_plan"] = []
    next_context["campaign_dynamics_analysis"] = {
        "period": {
            "dateTo": requested_date,
            "windows": {"selectedDate": {"dateFrom": requested_date, "dateTo": requested_date}},
            "requestedPeriods": ["selected_date"],
        },
        "dataQuality": {
            "rows": analysis.get("rows", 0),
            "campaigns": len(analysis.get("campaigns") or []),
            "hasGoalData": analysis["dataQuality"].get("hasGoalData", False),
            "missingDays": [],
            "limitations": analysis.get("missingData") or [],
        },
        "accountDynamics": {
            "last7": analysis["accountTotals"],
            "previous7": {},
            "last14": analysis["accountTotals"],
            "previous14": {},
            "last30": analysis["accountTotals"],
            "changes": {},
            "mainFindings": analysis.get("mainFindings") or [],
        },
        "campaignDynamics": {
            "worstCampaigns": [
                {
                    "campaignName": item.get("campaign_name"),
                    "severity": item.get("severity"),
                    "issueFlags": item.get("issue_flags"),
                    "last7": {
                        "cost": item.get("cost"),
                        "clicks": item.get("clicks"),
                        "impressions": item.get("impressions"),
                        "ctr": item.get("ctr"),
                        "avgCpc": item.get("avg_cpc"),
                        "goalConversions": item.get("goal_conversions"),
                        "goalCpa": item.get("goal_cpa"),
                    },
                    "changes": {"last7VsPrevious7": {}},
                }
                for item in analysis.get("campaigns", [])[:8]
            ],
            "bestCampaigns": [],
            "allCampaignsCompact": analysis.get("campaigns", [])[:20],
        },
        "drilldownPlan": analysis.get("drilldownPlan") or [],
        "recommendations": [],
        "missingData": analysis.get("missingData") or [],
        "safety": analysis.get("safety") or {},
    }
    return next_context


def _is_rate_limit_error(exc: HTTPException) -> bool:
    detail = exc.detail
    text = json.dumps(detail, ensure_ascii=False).lower() if isinstance(detail, (dict, list)) else str(detail).lower()
    return exc.status_code == 429 or "429" in text or "rate limit" in text or "rate-limited" in text or "temporarily rate" in text


def _normalized_ai_error(exc: HTTPException, model: str) -> dict[str, object] | None:
    if exc.status_code == 504 or (isinstance(exc.detail, dict) and exc.detail.get("error_code") == "openrouter_timeout"):
        return {
            "error": True,
            "error_code": "openrouter_timeout",
            "message": "Выбранная модель не успела сформировать ответ. Повторите запрос или временно выберите Mistral Small 3.2 · Эконом.",
            "model": model,
            "retryable": True,
            "suggested_preset": "economy",
        }
    if not _is_rate_limit_error(exc):
        return None
    return {
        "error": True,
        "error_code": "openrouter_rate_limited",
        "message": AI_RATE_LIMIT_MESSAGE,
        "model": model,
        "retryable": True,
        "suggested_preset": "economy",
    }


@router.get("/openrouter/status", response_model=AiStatusResponse)
def get_openrouter_status() -> dict[str, object]:
    return _ai_status_payload()


@router.post("/audits", response_model=AiAuditJobResponse, status_code=status.HTTP_202_ACCEPTED)
def create_staged_audit(
    payload: AiAuditCreateRequest,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> AiAuditJobResponse:
    job = create_audit_job(
        db,
        payload,
        organization_id=current.organization.id,
        user_id=current.user.id,
        user_email=current.email,
    )
    return audit_job_response(job)


@router.get("/audits/{job_id}", response_model=AiAuditJobResponse)
def read_staged_audit(
    job_id: str,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> AiAuditJobResponse:
    return audit_job_response(get_audit_job(db, job_id, organization_id=current.organization.id))


@router.post("/audits/{job_id}/advance", response_model=AiAuditJobResponse)
async def advance_staged_audit(
    job_id: str,
    payload: AiAuditAdvanceRequest | None = None,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> AiAuditJobResponse:
    job = await advance_audit_job(
        db,
        job_id,
        organization_id=current.organization.id,
        retry=bool(payload and payload.retry),
    )
    return audit_job_response(job)


@router.post("/audits/{job_id}/cancel", response_model=AiAuditJobResponse)
def cancel_staged_audit(
    job_id: str,
    db: Session = Depends(get_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> AiAuditJobResponse:
    return audit_job_response(cancel_audit_job(db, job_id, organization_id=current.organization.id))


@router.post("/openrouter/generate", response_model=AiPromptResponse)
async def generate_ai_response(
    payload: AiPromptRequest,
    current: CurrentUser = Depends(get_current_session_user),
) -> dict[str, object]:
    ai_options = _resolved_ai_options(payload.model, payload.ai_preset, payload.max_tokens)
    prompt = (
        f"{payload.prompt}\n\n"
        f"AI mode: {ai_options['ai_preset']}. Token budget: {ai_options['max_tokens']} "
        f"(cap {ai_options['max_tokens_cap']}). Keep the answer concise in economy mode; "
        "advanced mode may use deeper structured analysis."
    )
    selected_model = str(ai_options["model"])
    request_debug = build_openrouter_request_debug(
        mode="model_test",
        endpoint="/api/v1/ai/openrouter/generate",
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt=prompt,
        model=selected_model,
        max_tokens=int(ai_options["max_tokens"]),
        context={"prompt": payload.prompt},
        compact_options={"ai_preset": ai_options["ai_preset"]},
        include_preview=True,
    )
    try:
        result = await generate_openrouter_response(
            model=selected_model,
            prompt=prompt,
            max_tokens=int(ai_options["max_tokens"]),
        )
        if payload.inspect_request:
            result["requestDebug"] = request_debug
        return result
    except HTTPException as exc:
        normalized = _normalized_ai_error(exc, selected_model)
        if normalized:
            payload_out = {"content": "", **normalized}
            payload_out["requestDebug"] = request_debug
            return payload_out
        raise


@router.post("/chat", response_model=AiChatResponse)
async def chat_with_ai(
    payload: AiChatRequest,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> AiChatResponse:
    request_started_at = perf_counter()
    if requires_staged_audit(payload.message):
        return AiChatResponse(
            client_id=payload.client_id,
            model=payload.model or DEFAULT_PRODUCTION_AI_MODEL,
            source="staged_audit_router",
            answer="Полный аудит выполняется как отдельная поэтапная задача.",
            tool_traces=[],
            error=True,
            error_code="staged_audit_required",
            message="Полный аудит выполняется как отдельная поэтапная задача.",
            retryable=False,
            suggested_action="create_audit_job",
        )
    requested_date = _parse_specific_date_request(payload.message)
    chat_message = _single_day_prompt_message(payload.message, requested_date) if requested_date else payload.message
    ai_options = _apply_specific_date_token_floor(
        _apply_intent_token_floor(
            _resolved_ai_options(payload.model, payload.ai_preset, payload.max_tokens),
            message=chat_message,
            explicit_max_tokens=payload.max_tokens is not None,
        ),
        requested_date=requested_date,
        explicit_max_tokens=payload.max_tokens is not None,
    )
    server_context = payload.client_context
    specific_date_analysis: dict[str, Any] | None = None
    context_started_at = perf_counter()
    specific_date_fetch_ms = 0
    if db is not None:
        client = db.get(ClientAccount, payload.client_id)
        if not client or client.organization_id != current.organization.id:
            raise HTTPException(status_code=404, detail="Client not found")
        server_context = build_client_ai_context_from_db(db, payload.client_id, selected_campaign_name=payload.selected_campaign_name)
        if requested_date:
            specific_date_started_at = perf_counter()
            specific_date_analysis = _fetch_specific_date_analysis(db, client, requested_date)
            specific_date_fetch_ms = round((perf_counter() - specific_date_started_at) * 1000)
            server_context = _apply_specific_date_analysis_to_context(server_context, specific_date_analysis)
    compacted_context = compact_client_context_for_chat(
        server_context,
        compact_context=payload.compact_context,
        search_query_limit=payload.search_query_limit,
        selected_campaign_name=payload.selected_campaign_name,
    )
    context_build_ms = round((perf_counter() - context_started_at) * 1000)
    selected_model = str(ai_options["model"])
    try:
        response = await answer_ai_chat(
            client_id=payload.client_id,
            message=chat_message,
            model=selected_model,
            history=payload.history,
            client_context=compacted_context,
            max_tokens=int(ai_options["max_tokens"]),
            compact_context=payload.compact_context,
            tool_results_mode=payload.tool_results_mode,
            chat_history_limit=payload.chat_history_limit,
            search_query_limit=payload.search_query_limit,
            selected_campaign_name=payload.selected_campaign_name,
            inspect_request=payload.inspect_request,
            initial_timings={
                "contextBuildMs": context_build_ms,
                "specificDateFetchMs": specific_date_fetch_ms,
            },
            request_started_at=request_started_at,
        )
        return _decorate_specific_date_response_trace(
            response,
            requested_date=requested_date,
            analysis=specific_date_analysis,
            original_message=payload.message,
        )
    except HTTPException as exc:
        normalized = _normalized_ai_error(exc, selected_model)
        if normalized:
            normalized_response = {key: value for key, value in normalized.items() if key != "model"}
            return AiChatResponse(
                client_id=payload.client_id,
                model=selected_model,
                source="openrouter_error_normalized",
                answer=str(normalized["message"]),
                tool_traces=[],
                **normalized_response,
            )
        raise
