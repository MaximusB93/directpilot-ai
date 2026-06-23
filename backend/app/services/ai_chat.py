import copy
import json
from typing import Any

from fastapi import HTTPException

from app.core.config import settings
from app.mcp.tools import call_tool
from app.schemas import AiChatMessage, AiChatResponse, AiToolTrace
from app.services.ai_prompt_debug import build_openrouter_request_debug, build_prompt_debug_snapshot, estimate_tokens
from app.services.direct_analyst_playbook import build_direct_analyst_instructions
from app.services.openrouter import DEFAULT_SYSTEM_PROMPT, generate_openrouter_response, redact_openrouter_debug_payload

BASE_TOOL_PLAN = [
    ("get_client", lambda client_id: {"client_id": client_id}),
    ("list_campaigns", lambda client_id: {"client_id": client_id}),
    ("list_audit_issues", lambda client_id: {"client_id": client_id}),
    ("list_recommendations", lambda client_id: {"client_id": client_id}),
]


def _select_mcp_tools(message: str) -> list[tuple[str, Any]]:
    normalized = message.lower()
    tool_plan = list(BASE_TOOL_PLAN)
    if any(token in normalized for token in ["метрик", "metrica", "цель", "конверси"]):
        tool_plan.append(("list_yandex_metrica_goals", lambda client_id: {"client_id": client_id}))
    if any(token in normalized for token in ["директ", "direct", "кампан", "расход", "cpa", "ставк"]):
        tool_plan.append(("list_yandex_direct_campaigns", lambda client_id: {"client_id": client_id}))
    if any(token in normalized for token in ["интеграц", "подключ", "oauth"]):
        tool_plan.append(("list_integrations", lambda client_id: {}))
    if any(token in normalized for token in ["metrica", "метрик", "цель", "цели", "конверс"]):
        tool_plan.append(("list_yandex_metrica_goals", lambda client_id: {"client_id": client_id}))
    if any(token in normalized for token in ["direct", "директ", "кампан", "расход", "cpa", "ставк", "запрос"]):
        tool_plan.append(("list_yandex_direct_campaigns", lambda client_id: {"client_id": client_id}))
    if any(token in normalized for token in ["интеграц", "подключ", "oauth"]):
        tool_plan.append(("list_integrations", lambda client_id: {}))
    deduped: list[tuple[str, Any]] = []
    seen: set[str] = set()
    for name, factory in tool_plan:
        if name not in seen:
            deduped.append((name, factory))
            seen.add(name)
    return deduped


def _local_tool_result(name: str, client_id: str, client_context: dict[str, Any] | None) -> Any:
    client = client_context or {"id": client_id, "name": client_id, "directLogin": "Не подключен", "metricaCounter": "Не подключен"}
    if name == "get_client":
        return client
    if name in {"list_campaigns", "list_yandex_direct_campaigns", "list_audit_issues", "list_recommendations"}:
        return []
    if name == "list_yandex_metrica_goals":
        return [
            {
                "client_id": client.get("id", client_id),
                "counter_id": client.get("metricaCounter", "Не подключен"),
                "goal_id": None,
                "name": "Цели нужно загрузить из Метрики",
                "status": "awaiting_real_metrica_connection",
            }
        ]
    if name == "list_integrations":
        return []
    return {"message": "Нет локального результата для MCP tool"}


def _run_mcp_tools(client_id: str, message: str, client_context: dict[str, Any] | None = None) -> list[AiToolTrace]:
    traces: list[AiToolTrace] = []
    for name, args_factory in _select_mcp_tools(message):
        arguments = args_factory(client_id)
        try:
            result = call_tool(name, arguments)
        except ValueError:
            result = _local_tool_result(name=name, client_id=client_id, client_context=client_context)
        traces.append(AiToolTrace(name=name, arguments=arguments, result=result))
    return traces


def _limit_history(messages: list[AiChatMessage], chat_history_limit: int | None) -> list[AiChatMessage]:
    limit = 3 if chat_history_limit is None else max(0, min(int(chat_history_limit), 8))
    return messages[-limit:] if limit else []


def _brief_value(value: Any, depth: int = 0) -> Any:
    if depth > 1:
        return "... omitted ..."
    if isinstance(value, list):
        return {
            "type": "list",
            "count": len(value),
            "sample": [_brief_value(item, depth + 1) for item in value[:3]],
            "note": "full result omitted to reduce prompt size",
        }
    if isinstance(value, dict):
        keys = list(value.keys())
        return {
            "type": "object",
            "keys": keys[:10],
            "sample": {key: _brief_value(value[key], depth + 1) for key in keys[:3]},
            "note": "full result omitted to reduce prompt size",
        }
    text = str(value)
    return text[:500] + ("... omitted ..." if len(text) > 500 else "")


def _tool_trace_for_prompt(trace: AiToolTrace, tool_results_mode: str = "summary") -> dict[str, Any]:
    if tool_results_mode == "full":
        return trace.model_dump()
    return {
        "name": trace.name,
        "arguments": trace.arguments,
        "result_summary": _brief_value(trace.result),
        "full_result_omitted": True,
    }


def _limit_search_query_insights(value: Any, limit: int | None) -> Any:
    if not isinstance(value, dict) or limit is None:
        return value
    limited = copy.deepcopy(value)
    for key in ("insights", "items", "queries", "candidateNegativeKeywords"):
        if isinstance(limited.get(key), list):
            limited[key] = limited[key][:limit]
    return limited


def compact_client_context_for_chat(
    client_context: dict[str, Any] | None,
    *,
    compact_context: bool = True,
    search_query_limit: int | None = 20,
    selected_campaign_name: str | None = None,
) -> dict[str, Any] | None:
    if not client_context:
        return client_context
    if not compact_context:
        return copy.deepcopy(client_context)
    if search_query_limit is not None and search_query_limit <= 0:
        search_query_limit = None

    context = copy.deepcopy(client_context)
    summary = context.get("summary") if isinstance(context.get("summary"), dict) else {}
    if summary:
        summary["searchQueryInsights"] = _limit_search_query_insights(summary.get("searchQueryInsights"), search_query_limit)
        if isinstance(summary.get("campaigns"), list) and not selected_campaign_name:
            summary["campaigns"] = summary["campaigns"][:10]
        context["summary"] = summary
    context["search_query_insights"] = _limit_search_query_insights(context.get("search_query_insights"), search_query_limit)
    if isinstance(context.get("campaigns"), list) and not selected_campaign_name:
        context["campaigns"] = context["campaigns"][:10]
    if isinstance(context.get("diagnostics"), list) and not selected_campaign_name:
        context["diagnostics"] = context["diagnostics"][:10]
    if isinstance(context.get("optimization_plan"), list):
        context["optimization_plan"] = context["optimization_plan"][:10]
    if isinstance(context.get("knowledge_snippets"), list):
        context["knowledge_snippets"] = context["knowledge_snippets"][:3]

    saved_actions = context.get("saved_optimization_actions")
    if isinstance(saved_actions, dict):
        for key in ("approved", "rejected", "needs_changes", "latest_comments"):
            if isinstance(saved_actions.get(key), list):
                saved_actions[key] = saved_actions[key][:3]
        context["saved_optimization_actions"] = saved_actions

    context["context_compaction"] = {
        "enabled": True,
        "search_query_limit": search_query_limit,
        "selected_campaign_name": selected_campaign_name,
        "note": "Large lists were trimmed for AI chat prompt budget. Source data is not mutated.",
    }
    return context


def _first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, "", [], {}):
            return value
    return None


def _number_or_none(value: Any) -> float | int | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return int(number) if number.is_integer() else number


def _compact_text(value: Any, limit: int = 500) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:limit] + ("..." if len(text) > limit else "")


def _list_head(value: Any, limit: int = 5) -> list[Any]:
    return value[:limit] if isinstance(value, list) else []


def _normal_text(value: str) -> str:
    return (value or "").lower().replace("ё", "е")


def detect_analysis_intent(message: str) -> dict[str, Any]:
    text = _normal_text(message)
    notes: list[str] = []
    requested_period: str | None = None
    if "за вчера" in text or "вчера" in text:
        requested_period = "yesterday"
    elif "за последние 7" in text or "7 дней" in text:
        requested_period = "last_7_days"
    elif "за неделю" in text or "недел" in text:
        requested_period = "week"
    elif "за месяц" in text or "месяц" in text:
        requested_period = "month"
    elif "за май" in text:
        requested_period = "may"
    else:
        notes.append("Requested period was not parsed; use latest synced period.")

    rules = [
        (
            "campaign_dynamics_analysis",
            [
                "динамика",
                "последние 7",
                "последние 14",
                "последние 30",
                "7 дней",
                "14 дней",
                "30 дней",
                "изменения",
                "ухудшились",
                "улучшились",
                "рост",
                "падение",
                "тренд",
                "что изменилось",
                "dynamics",
                "trend",
                "last 7",
                "last 14",
                "last 30",
            ],
            ["campaign_dynamics", "daily_campaign_stats", "selected_goals", "campaigns"],
            False,
        ),
        (
            "global_direct_audit",
            ["аудит", "чеклист", "чек-лист", "полный анализ", "весь аккаунт", "комплексный анализ"],
            ["account_summary", "campaigns", "audit", "search_queries", "dynamics", "demographics"],
            True,
        ),
        (
            "search_queries_analysis",
            ["поисковые запросы", "запросы", "search query", "минус-слова", "минуса"],
            ["search_queries", "selected_goals", "campaigns"],
            False,
        ),
        (
            "dynamics_analysis",
            ["динамика", "по дням", "неделя", "месяц", "вчера", "рост", "падение"],
            ["daily_summary", "sync_period", "campaigns"],
            False,
        ),
        (
            "demographics_analysis",
            ["пол", "возраст", "демография", "соцдем", "устройства", "гео", "регион"],
            ["demographics", "geo", "devices"],
            False,
        ),
        (
            "goal_tracking_analysis",
            ["цели", "метрика", "конверсии", "goal", "tracking"],
            ["selected_goals", "conversion_source", "tracking_warnings"],
            False,
        ),
        (
            "campaign_analysis",
            ["кампания", "кампанию", "campaign", "high cpa", "cpa", "расход"],
            ["campaigns", "account_summary", "selected_goals"],
            False,
        ),
    ]
    for intent, tokens, data_needs, requires_cascade in rules:
        if any(token in text for token in tokens):
            return {
                "intent": intent,
                "scope": "whole_account" if intent in {"global_direct_audit", "search_queries_analysis"} else "focused",
                "requiresCascade": requires_cascade,
                "requestedPeriod": requested_period,
                "dataNeeds": data_needs,
                "notes": notes,
            }
    return {
        "intent": "general_question",
        "scope": "focused",
        "requiresCascade": False,
        "requestedPeriod": requested_period,
        "dataNeeds": ["client", "account_summary"],
        "notes": notes,
    }


def _client_data(context: dict[str, Any]) -> dict[str, Any]:
    client = context.get("client") if isinstance(context.get("client"), dict) else context
    return client if isinstance(client, dict) else {}


def _business_context_data(context: dict[str, Any]) -> dict[str, Any]:
    business = context.get("business_context")
    if isinstance(business, dict):
        fields = business.get("fields")
        return fields if isinstance(fields, dict) else business
    return {}


def classify_search_query(query: str, client_context: dict[str, Any] | None) -> dict[str, Any]:
    context = client_context if isinstance(client_context, dict) else {}
    client = _client_data(context)
    business = _business_context_data(context)
    raw_tokens = [
        client.get("name"),
        client.get("directLogin"),
        client.get("direct_login"),
        business.get("brandName"),
        business.get("brand_name"),
        business.get("brand"),
        "green flow",
        "greenflow",
        "грин флоу",
        "гринфлоу",
    ]
    tokens: set[str] = set()
    for token in raw_tokens:
        text = _normal_text(str(token or "")).strip()
        if len(text) >= 3 and text not in {"none", "null"}:
            tokens.add(text)
            tokens.add(text.replace(" ", ""))
    normalized_query = _normal_text(query)
    brand_like = any(token and token in normalized_query.replace(" ", "") for token in tokens)
    return {
        "query": query,
        "brandLike": brand_like,
        "risk": "high" if brand_like else "normal",
        "classification": "brand_or_tracking_review" if brand_like else "non_brand_query",
        "safeNegativeKeyword": not brand_like,
        "brandTokensMatched": sorted(token for token in tokens if token and token in normalized_query.replace(" ", ""))[:5],
    }


def _compact_campaign(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": _first_present(item.get("campaign_name"), item.get("name")),
        "cost": _number_or_none(item.get("cost")),
        "impressions": _number_or_none(item.get("impressions")),
        "clicks": _number_or_none(item.get("clicks")),
        "ctr": _number_or_none(item.get("ctr")),
        "avgCpc": _number_or_none(_first_present(item.get("avg_cpc"), item.get("avgCpc"))),
        "goalConversions": _number_or_none(_first_present(item.get("goal_conversions"), item.get("goalConversions"), item.get("conversionsUsed"))),
        "goalCpa": _number_or_none(_first_present(item.get("goal_cpa"), item.get("goalCpa"), item.get("cpaUsed"))),
        "severity": _first_present(item.get("severity"), "info"),
        "issueFlags": item.get("issue_flags") or item.get("issueFlags") or [],
        "recommendedFocus": item.get("recommended_focus") or item.get("recommendedFocus"),
    }


def _compact_search_query(item: dict[str, Any], client_context: dict[str, Any]) -> dict[str, Any]:
    query = str(_first_present(item.get("query"), item.get("search_query"), item.get("searchQuery"), "") or "")
    goal_conversions = _number_or_none(_first_present(item.get("goal_conversions"), item.get("goalConversions"), item.get("conversionsUsed"))) or 0
    classified = classify_search_query(query, client_context)
    if goal_conversions > 0:
        classified["safeNegativeKeyword"] = False
        classified["classification"] = "has_goal_conversions"
        classified["risk"] = "high"
    return {
        "query": query,
        "campaign": _first_present(item.get("campaign_name"), item.get("campaign"), item.get("campaignName")),
        "adGroup": _first_present(item.get("ad_group_name"), item.get("adGroupName")),
        "cost": _number_or_none(item.get("cost")),
        "clicks": _number_or_none(item.get("clicks")),
        "impressions": _number_or_none(item.get("impressions")),
        "goalConversions": goal_conversions,
        "totalConversions": _number_or_none(_first_present(item.get("conversions"), item.get("totalConversions"))),
        "reason": item.get("reason") or item.get("recommendation_reason") or item.get("recommendationReason"),
        "confidence": item.get("confidence"),
        "recommendedNegativeKeyword": item.get("recommended_negative_keyword") or item.get("recommendedNegativeKeyword") or query,
        **classified,
    }


def _compact_dynamics_campaign(item: dict[str, Any]) -> dict[str, Any]:
    last7 = item.get("last7") if isinstance(item.get("last7"), dict) else {}
    changes = (item.get("changes") or {}).get("last7VsPrevious7") if isinstance(item.get("changes"), dict) else {}
    return {
        "campaignName": item.get("campaignName"),
        "severity": item.get("severity"),
        "issueFlags": item.get("issueFlags") or [],
        "last7": {
            "cost": _number_or_none(last7.get("cost")),
            "clicks": _number_or_none(last7.get("clicks")),
            "impressions": _number_or_none(last7.get("impressions")),
            "ctr": _number_or_none(last7.get("ctr")),
            "avgCpc": _number_or_none(last7.get("avgCpc")),
            "goalConversions": _number_or_none(last7.get("goalConversions")),
            "goalCpa": _number_or_none(last7.get("goalCpa")),
        },
        "changes": {
            "costDeltaPct": _number_or_none((changes or {}).get("costDeltaPct")),
            "clicksDeltaPct": _number_or_none((changes or {}).get("clicksDeltaPct")),
            "ctrDeltaPct": _number_or_none((changes or {}).get("ctrDeltaPct")),
            "avgCpcDeltaPct": _number_or_none((changes or {}).get("avgCpcDeltaPct")),
            "goalConversionsDeltaPct": _number_or_none((changes or {}).get("goalConversionsDeltaPct")),
            "goalCpaDeltaPct": _number_or_none((changes or {}).get("goalCpaDeltaPct")),
        },
    }


def _compact_campaign_dynamics(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {"available": False, "missingData": ["Campaign dynamics analysis is missing."]}
    data_quality = value.get("dataQuality") if isinstance(value.get("dataQuality"), dict) else {}
    account = value.get("accountDynamics") if isinstance(value.get("accountDynamics"), dict) else {}
    campaigns = value.get("campaignDynamics") if isinstance(value.get("campaignDynamics"), dict) else {}
    return {
        "available": bool(data_quality.get("rows")),
        "period": value.get("period") or {},
        "dataQuality": {
            "rows": data_quality.get("rows", 0),
            "campaigns": data_quality.get("campaigns", 0),
            "hasGoalData": bool(data_quality.get("hasGoalData")),
            "missingDays": _list_head(data_quality.get("missingDays"), 10),
            "limitations": _list_head(data_quality.get("limitations"), 8),
        },
        "accountDynamics": {
            "last7": account.get("last7"),
            "previous7": account.get("previous7"),
            "last14": account.get("last14"),
            "previous14": account.get("previous14"),
            "last30": account.get("last30"),
            "changes": account.get("changes"),
            "mainFindings": _list_head(account.get("mainFindings"), 8),
        },
        "worstCampaigns": [
            _compact_dynamics_campaign(item)
            for item in _list_head(campaigns.get("worstCampaigns"), 8)
            if isinstance(item, dict)
        ],
        "bestCampaigns": [
            _compact_dynamics_campaign(item)
            for item in _list_head(campaigns.get("bestCampaigns"), 8)
            if isinstance(item, dict)
        ],
        "drilldownPlan": _list_head(value.get("drilldownPlan"), 8),
        "recommendations": _list_head(value.get("recommendations"), 8),
        "missingData": _list_head(value.get("missingData"), 8),
    }


def build_compact_ai_chat_context(
    client_context: dict[str, Any] | None,
    intent_plan: dict[str, Any],
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    context = client_context if isinstance(client_context, dict) else {}
    summary = context.get("summary") if isinstance(context.get("summary"), dict) else {}
    client = _client_data(context)
    business = _business_context_data(context)
    goals = context.get("goals") if isinstance(context.get("goals"), dict) else {}
    diagnostics = summary.get("syncDiagnostics") or context.get("sync_diagnostics") or {}
    selected_goal_ids = (
        summary.get("selectedGoalIds")
        or goals.get("selected_goal_ids")
        or context.get("selectedGoalIds")
        or []
    )
    campaigns_source = context.get("campaigns") or summary.get("campaigns") or []
    campaigns = [_compact_campaign(item) for item in _list_head(campaigns_source, 12) if isinstance(item, dict)]
    search_source = summary.get("searchQueryInsights") or context.get("search_query_insights") or {}
    dynamics_source = context.get("campaign_dynamics_analysis") or summary.get("campaignDynamicsAnalysis") or {}
    intent_name = intent_plan.get("intent")
    search_items = search_source.get("insights") if isinstance(search_source, dict) else []
    compact_queries = [_compact_search_query(item, context) for item in _list_head(search_items, int((options or {}).get("search_query_limit") or 20)) if isinstance(item, dict)]
    brand_queries = [item for item in compact_queries if item.get("brandLike")][:10]
    non_brand_waste = [item for item in compact_queries if not item.get("brandLike") and not item.get("goalConversions")][:10]
    queries_with_goals = [item for item in compact_queries if (item.get("goalConversions") or 0) > 0][:10]
    audit = summary.get("yandexDirectAudit") or context.get("yandex_direct_audit") or {}
    saved_actions = context.get("saved_optimization_actions") if isinstance(context.get("saved_optimization_actions"), dict) else {}
    memory_notes = business.get("memoryNotes") or business.get("memory_notes")
    limitations = []
    omitted_sections = [
        "yandex_binding.account ids/timestamps",
        "latest_sync_job ids/timestamps",
        "full direct_analyst_playbook",
        "full audit checks",
        "duplicate root summary/search query/audit sections",
        "full previous AI memory_notes",
    ]
    if memory_notes:
        limitations.append("Previous AI memory is reference-only and must not override current trusted metrics.")
    if not selected_goal_ids:
        limitations.append("Selected goal IDs are missing.")
    if not summary and not campaigns:
        limitations.append("Performance summary is missing.")
    compact_dynamics = _compact_campaign_dynamics(dynamics_source)
    if intent_name == "campaign_dynamics_analysis":
        campaigns = [
            _compact_dynamics_campaign(item)
            for item in _list_head(((dynamics_source or {}).get("campaignDynamics") or {}).get("worstCampaigns"), 8)
            if isinstance(item, dict)
        ]
        compact_queries = []
        brand_queries = []
        non_brand_waste = []
        queries_with_goals = []
        audit = {}
        omitted_sections.extend(
            [
                "full audit details for campaign dynamics intent",
                "full search query dump for campaign dynamics intent",
                "optimization drafts for campaign dynamics intent",
            ]
        )
    return {
        "analysisPlan": intent_plan,
        "client": {
            "id": client.get("id"),
            "name": client.get("name"),
            "directLogin": client.get("directLogin") or client.get("direct_login"),
            "metricaCounter": client.get("metricaCounter") or client.get("metrica_counter"),
            "targetCpa": client.get("targetCpa") or client.get("target_cpa"),
            "businessContextStatus": context.get("businessContextStatus", {}).get("status") if isinstance(context.get("businessContextStatus"), dict) else ("partial" if business else "empty"),
        },
        "businessMemory": {
            "type": "previous_ai_memory",
            "available": bool(memory_notes),
            "trustLevel": "reference_only",
            "summary": _compact_text(memory_notes, 500),
        },
        "dataQuality": {
            "syncStatus": client.get("syncStatus") or client.get("sync_status"),
            "period": summary.get("period") or context.get("period"),
            "selectedGoalIds": selected_goal_ids,
            "hasGoalData": bool(summary.get("hasGoalData") or goals.get("has_goal_data")),
            "goalConversionsTotal": _number_or_none(summary.get("goalConversionsTotal") or goals.get("goal_conversions_total")),
            "message": summary.get("conversionsSourceMessage") or diagnostics.get("message"),
        },
        "accountTotals": {
            "cost": _number_or_none((summary.get("totals") or {}).get("cost")),
            "impressions": _number_or_none((summary.get("totals") or {}).get("impressions")),
            "clicks": _number_or_none((summary.get("totals") or {}).get("clicks")),
            "ctr": _number_or_none((summary.get("totals") or {}).get("ctr")),
            "avgCpc": _number_or_none((summary.get("totals") or {}).get("avgCpc")),
            "goalConversions": _number_or_none(summary.get("goalConversionsTotal")),
            "goalCpa": _number_or_none((summary.get("totals") or {}).get("goalCpa") or (summary.get("totals") or {}).get("cpa")),
        },
        "campaigns": campaigns,
        "audit": {
            "score": audit.get("score"),
            "grade": audit.get("grade"),
            "summary": audit.get("summary"),
            "categoryScores": [
                {
                    "title": item.get("title"),
                    "score": item.get("score"),
                    "grade": item.get("grade"),
                    "status": item.get("status"),
                }
                for item in _list_head(audit.get("categories"), 8)
                if isinstance(item, dict)
            ],
            "criticalIssues": _list_head(audit.get("criticalIssues"), 8),
            "quickWins": _list_head(audit.get("quickWins"), 8),
            "limitations": _list_head(audit.get("limitations"), 8),
        },
        "searchQueries": {
            "totalQueries": search_source.get("totalQueries") if isinstance(search_source, dict) else len(compact_queries),
            "candidateNegativeKeywords": search_source.get("candidateNegativeKeywords") if isinstance(search_source, dict) else len(non_brand_waste),
            "totalWasteCost": search_source.get("totalWasteCost") if isinstance(search_source, dict) else None,
            "topWasteQueries": compact_queries[:10],
            "brandLikeQueries": brand_queries,
            "nonBrandWasteQueries": non_brand_waste,
            "queriesWithGoalConversions": queries_with_goals,
        },
        "campaignDynamicsAnalysis": compact_dynamics,
        "dynamics": {
            "available": bool(compact_dynamics.get("available") or summary.get("yesterdayCampaignSummary") or context.get("yesterday_campaign_summary")),
            "summary": "Campaign dynamics analysis is available." if compact_dynamics.get("available") else "Daily/weekly dynamics are not fully available.",
            "dailyRows": _list_head((summary.get("yesterdayCampaignSummary") or {}).get("campaigns"), 10),
        },
        "demographics": {
            "available": False,
            "summary": "Demographics/geo/device breakdown is not loaded yet.",
            "segments": [],
        },
        "optimizationDrafts": {
            "total": saved_actions.get("total", 0),
            "draft": saved_actions.get("draft", 0),
            "appliedToYandex": False,
            "topActions": _list_head(context.get("optimization_plan"), 8),
        },
        "knowledgeRules": [
            {"title": item.get("title"), "content": _compact_text(item.get("content"), 300)}
            for item in _list_head(context.get("knowledge_snippets"), 3)
            if isinstance(item, dict)
        ],
        "limitations": limitations,
        "safety": {
            "noWriteActions": True,
            "message": "Изменения в Яндекс.Директ не применялись.",
        },
        "omittedSections": omitted_sections,
    }


def _build_data_fetch_trace(compact_prompt_context: dict[str, Any]) -> list[dict[str, Any]]:
    search_queries = compact_prompt_context.get("searchQueries") if isinstance(compact_prompt_context, dict) else {}
    campaigns = compact_prompt_context.get("campaigns") if isinstance(compact_prompt_context, dict) else []
    audit = compact_prompt_context.get("audit") if isinstance(compact_prompt_context, dict) else {}
    data_quality = compact_prompt_context.get("dataQuality") if isinstance(compact_prompt_context, dict) else {}
    memory = compact_prompt_context.get("businessMemory") if isinstance(compact_prompt_context, dict) else {}
    dynamics = compact_prompt_context.get("campaignDynamicsAnalysis") if isinstance(compact_prompt_context, dict) else {}
    return [
        {
            "source": "cached_direct_sync_data",
            "status": "used" if campaigns else "missing",
            "rows": len(campaigns) if isinstance(campaigns, list) else 0,
        },
        {
            "source": "cached_campaign_daily_stats",
            "status": "used" if (dynamics or {}).get("available") else "missing",
            "rows": ((dynamics or {}).get("dataQuality") or {}).get("rows", 0),
        },
        {
            "source": "deterministic_campaign_dynamics_analyzer",
            "status": "used" if (dynamics or {}).get("available") else "missing",
            "rows": ((dynamics or {}).get("dataQuality") or {}).get("campaigns", 0),
        },
        {
            "source": "yandex_direct_campaign_daily_range_report",
            "status": "cached" if (dynamics or {}).get("available") else "not_loaded",
            "rows": ((dynamics or {}).get("dataQuality") or {}).get("rows", 0),
            "message": "Daily range report is fetched during sync and reused from cache in AI chat.",
        },
        {
            "source": "cached_search_query_insights",
            "status": "used" if (search_queries or {}).get("topWasteQueries") else "missing",
            "rows": len((search_queries or {}).get("topWasteQueries") or []),
        },
        {
            "source": "cached_goal_data",
            "status": "used" if (data_quality or {}).get("hasGoalData") else "missing",
            "rows": 1 if (data_quality or {}).get("hasGoalData") else 0,
        },
        {
            "source": "deterministic_yandex_direct_audit",
            "status": "used" if (audit or {}).get("score") is not None else "missing",
            "rows": len((audit or {}).get("criticalIssues") or []) + len((audit or {}).get("quickWins") or []),
        },
        {
            "source": "business_context_reference_only_memory",
            "status": "used" if (memory or {}).get("available") else "missing",
            "rows": 1 if (memory or {}).get("available") else 0,
        },
        {
            "source": "yandex_direct_read_only_report",
            "status": "not_implemented",
            "rows": 0,
            "message": "Read-only search query fetch by arbitrary period is not implemented yet; using cached sync context.",
        },
    ]


def _format_history(messages: list[AiChatMessage], chat_history_limit: int | None = 3) -> str:
    messages = _limit_history(messages, chat_history_limit)
    if not messages:
        return "Истории диалога пока нет."
    return "\n".join(f"{item.role}: {item.content}" for item in messages)


def _build_chat_prompt(
    client_id: str,
    message: str,
    history: list[AiChatMessage],
    traces: list[AiToolTrace],
    *,
    compact_prompt_context: dict[str, Any] | None = None,
    intent_plan: dict[str, Any] | None = None,
    tool_results_mode: str = "summary",
    chat_history_limit: int | None = 3,
) -> str:
    tool_context = [_tool_trace_for_prompt(trace, tool_results_mode=tool_results_mode) for trace in traces]
    plan = intent_plan or detect_analysis_intent(message)
    compact_context = compact_prompt_context or {}
    if plan.get("intent") == "global_direct_audit":
        output_instructions = (
            "Выполни каскадный анализ: 1) качество данных и цели; 2) аккаунт целиком; "
            "3) кампании; 4) поисковые запросы; 5) динамика, если доступна; "
            "6) демография/гео/устройства, если доступны; 7) ограничения; "
            "8) безопасный план действий."
        )
    elif plan.get("intent") == "campaign_dynamics_analysis":
        output_instructions = (
            "Разбери динамику от общего к частному: 1) качество дневных данных и ограничения; "
            "2) аккаунт за last7/previous7, last14/previous14 и last30; "
            "3) кампании с ухудшением и улучшением; 4) вероятные причины изменений; "
            "5) какие данные нужны для drill-down: запросы, ключи, объявления, устройства, гео, демография; "
            "6) безопасный план улучшений. Не утверждай тренд, если данных недостаточно. "
            "Используй только selected goal conversions, CPA by goals, CTR, CPC, cost and clicks."
        )
    elif plan.get("intent") == "search_queries_analysis":
        output_instructions = (
            "Фокусируйся на поисковых запросах за requestedPeriod/currentPeriod: раздели брендовые и небрендовые; "
            "не предлагай брендовые как обычные минус-слова; не минусуй запросы с goalConversions > 0; "
            "покажи расход, клики, конверсии по выбранным целям, риск и уверенность."
        )
    else:
        output_instructions = "Ответь по задаче пользователя на основе compact trusted context. Если данных нет, явно перечисли limitations/missingData."
    return f"""
Ты AI-аналитик DirectPilot AI внутри чата PPC-специалиста.
Отвечай по-русски, структурно и только по trusted context ниже.
Не выдумывай метрики, конверсии, причины или факты. Если данных нет, добавь их в limitations/missingData.
Не применяй изменения и не говори, что изменения уже внесены: только аналитика, dry-run, рекомендации и approval.

client_id: {client_id}
История диалога:
{_format_history(history, chat_history_limit)}

Raw user task:
{message}

Analysis plan:
{json.dumps(plan, ensure_ascii=False, indent=2)}

Compact trusted context:
{json.dumps(compact_context, ensure_ascii=False, indent=2)}

Tool summaries:
{json.dumps(tool_context, ensure_ascii=False, indent=2)}

Output instructions:
{output_instructions}
""".strip()


def build_enriched_chat_message(message: str, server_context: dict[str, Any] | None, ai_options: dict[str, Any]) -> str:
    if not server_context:
        return message
    if (server_context.get("context_compaction") or {}).get("enabled"):
        playbook = (
            "Compact DirectPilot playbook: 1) check data quality and selected goals; "
            "2) use selected goal conversions and CPA by goals; 3) segment campaigns by severity; "
            "4) review search query intent and negative-keyword drafts; 5) return draft actions only; "
            "6) never claim Yandex Direct changes were applied."
        )
    else:
        playbook = build_direct_analyst_instructions(server_context)
    return (
        f"{message}\n\n"
        "Trusted server-side client context follows. Use it as the source of truth for client, campaigns, goals, "
        "sync state, diagnostics, and optimization drafts. Do not invent metrics, goal conversions, or applied "
        "changes. If goal data is missing, say it is missing. All Yandex actions are draft/manual-review only.\n"
        "Follow the DirectPilot analyst playbook in this order: data quality, goals, account overview, campaign "
        "segmentation, main issues, draft optimization actions, safety limitations.\n"
        f"DirectPilot analyst playbook:\n{playbook}\n"
        f"AI mode: {ai_options['ai_preset']}. Token budget: {ai_options['max_tokens']} "
        f"(cap {ai_options['max_tokens_cap']}). Keep answers concise in economy mode unless the user asks for detail; "
        "advanced mode may use deeper structured analysis.\n"
        f"{json.dumps(server_context, ensure_ascii=False, indent=2)}"
    )


def _build_chat_prompt_wrapper_context(client_id: str) -> dict[str, Any]:
    return {
        "role": "DirectPilot AI chat prompt wrapper",
        "client_id": client_id,
        "rules": [
            "Answer in Russian.",
            "Use only trusted context and MCP tool results.",
            "Do not claim changes were applied.",
            "Return draft/manual-review recommendations only.",
        ],
    }


def _build_server_context_debug_sections(server_context: dict[str, Any] | None) -> dict[str, Any]:
    context = server_context if isinstance(server_context, dict) else {}
    summary = context.get("summary") if isinstance(context.get("summary"), dict) else {}
    known = {
        "client",
        "business_context",
        "summary",
        "sync_diagnostics",
        "search_query_insights",
        "yesterday_campaign_summary",
        "yandex_direct_audit",
        "direct_analyst_playbook",
        "latest_sync_job",
        "goals",
        "yandex_binding",
        "campaigns",
        "diagnostics",
        "optimization_plan",
        "saved_optimization_actions",
        "knowledge_snippets",
        "selected_campaign_name",
        "selected_campaign",
        "warnings",
        "safety",
        "context_compaction",
    }
    return {
        "serverContext.client": context.get("client"),
        "serverContext.business_context": context.get("business_context"),
        "serverContext.summary": summary,
        "serverContext.summary.yesterdayCampaignSummary": summary.get("yesterdayCampaignSummary")
        or context.get("yesterday_campaign_summary"),
        "serverContext.summary.searchQueryInsights": summary.get("searchQueryInsights")
        or context.get("search_query_insights"),
        "serverContext.campaigns": context.get("campaigns"),
        "serverContext.diagnostics": context.get("diagnostics"),
        "serverContext.optimization": context.get("optimization_plan") or context.get("saved_optimization_actions"),
        "serverContext.knowledge_snippets": context.get("knowledge_snippets"),
        "serverContext.warnings": context.get("warnings"),
        "serverContext.other": {key: value for key, value in context.items() if key not in known},
    }


def _summarize_server_context_for_debug(server_context: dict[str, Any] | None) -> dict[str, Any]:
    context = server_context if isinstance(server_context, dict) else {}
    summary = context.get("summary") if isinstance(context.get("summary"), dict) else {}
    search_query_insights = summary.get("searchQueryInsights") or context.get("search_query_insights") or {}
    return {
        "available_sections": sorted(context.keys()),
        "campaigns_count": len(context.get("campaigns") or []),
        "has_business_context": bool(context.get("business_context")),
        "has_summary": bool(summary),
        "search_query_insights_count": len(search_query_insights.get("insights") or []),
        "warnings_count": len(context.get("warnings") or []),
    }


def _build_chat_debug_context(
    *,
    client_id: str,
    message: str,
    history: list[AiChatMessage],
    traces: list[AiToolTrace],
    client_context: dict[str, Any] | None,
    display_message: str | None = None,
    tool_results_mode: str = "summary",
    chat_history_limit: int | None = 3,
) -> dict[str, Any]:
    if client_context and ("analysisPlan" in client_context or (client_context.get("context_compaction") or {}).get("enabled")):
        playbook = "Compact DirectPilot playbook: data quality, goals, campaigns, search queries, draft actions, no applied changes."
    else:
        playbook = build_direct_analyst_instructions(client_context or {}) if client_context else ""
    context: dict[str, Any] = {
        "chat.message": display_message or message,
        "chat.history": [item.model_dump() for item in _limit_history(history, chat_history_limit)],
        "chat.playbook": playbook,
        "chat.serverContext": _summarize_server_context_for_debug(client_context),
        "chat.toolResults": [_tool_trace_for_prompt(trace, tool_results_mode=tool_results_mode) for trace in traces],
        "chat.finalPromptWrapper": _build_chat_prompt_wrapper_context(client_id),
    }
    context.update(_build_server_context_debug_sections(client_context))
    return context


def _count_items(value: Any) -> int | None:
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        for key in ("insights", "items", "campaigns", "actions"):
            if isinstance(value.get(key), list):
                return len(value[key])
    return None


def _tool_reason(name: str) -> str:
    return {
        "get_client": "Client identity and settings are always needed for client-aware chat.",
        "list_campaigns": "Campaign list helps answer account-level and campaign-level questions.",
        "list_audit_issues": "Audit issues provide deterministic evidence for the answer.",
        "list_recommendations": "Saved recommendations and drafts help avoid repeating stale advice.",
        "list_yandex_metrica_goals": "Goal context is relevant to conversion and CPA questions.",
        "list_yandex_direct_campaigns": "Direct campaign metrics are relevant to PPC analysis questions.",
        "list_integrations": "Integration state explains whether data can be trusted or synced.",
    }.get(name, "Selected by DirectPilot chat routing.")


def _tool_source(name: str) -> str:
    return {
        "get_client": "DirectPilot client context",
        "list_campaigns": "DirectPilot campaign context",
        "list_audit_issues": "DirectPilot audit context",
        "list_recommendations": "DirectPilot recommendation context",
        "list_yandex_metrica_goals": "DirectPilot Metrika context",
        "list_yandex_direct_campaigns": "DirectPilot Direct context",
        "list_integrations": "DirectPilot integration context",
    }.get(name, "DirectPilot local MCP tool")


def _result_summary(value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        first = value[0] if value else None
        return {
            "type": "list",
            "count": len(value),
            "keys": list(first.keys())[:10] if isinstance(first, dict) else [],
        }
    if isinstance(value, dict):
        return {"type": "object", "count": _count_items(value), "keys": list(value.keys())[:10]}
    return {"type": type(value).__name__, "count": None, "keys": []}


def _context_client_summary(context: dict[str, Any] | None) -> dict[str, Any]:
    data = context if isinstance(context, dict) else {}
    client = data.get("client") if isinstance(data.get("client"), dict) else {}
    return {
        "id": client.get("id"),
        "name": client.get("name"),
        "directLogin": client.get("direct_login") or client.get("directLogin"),
        "metricaCounter": client.get("metrica_counter") or client.get("metricaCounter"),
        "syncStatus": client.get("sync_status") or client.get("syncStatus"),
    }


def _tool_trace_entry(trace: AiToolTrace, tool_results_mode: str) -> dict[str, Any]:
    prompt_value = _tool_trace_for_prompt(trace, tool_results_mode=tool_results_mode)
    prompt_text = json.dumps(prompt_value, ensure_ascii=False, default=str)
    return {
        "name": trace.name,
        "selected": True,
        "reason": _tool_reason(trace.name),
        "arguments": redact_openrouter_debug_payload(trace.arguments),
        "source": _tool_source(trace.name),
        "resultSummary": _result_summary(trace.result),
        "includedInPrompt": "full" if tool_results_mode == "full" else "summary",
        "estimatedTokens": estimate_tokens(prompt_text),
    }


def _build_compaction_trace(
    *,
    original_context: dict[str, Any] | None,
    compacted_context: dict[str, Any] | None,
    history: list[AiChatMessage],
    chat_history_limit: int | None,
    tool_results_mode: str,
    search_query_limit: int | None,
    selected_campaign_name: str | None,
) -> list[dict[str, Any]]:
    original = original_context if isinstance(original_context, dict) else {}
    compacted = compacted_context if isinstance(compacted_context, dict) else {}
    original_summary = original.get("summary") if isinstance(original.get("summary"), dict) else {}
    compacted_summary = compacted.get("summary") if isinstance(compacted.get("summary"), dict) else {}
    original_search = original_summary.get("searchQueryInsights") or original.get("search_query_insights")
    compacted_search = compacted_summary.get("searchQueryInsights") or compacted.get("search_query_insights")
    return [
        {
            "section": "chat.history",
            "before": len(history),
            "after": len(_limit_history(history, chat_history_limit)),
            "rule": f"last {chat_history_limit if chat_history_limit is not None else 3} messages",
        },
        {
            "section": "serverContext.campaigns",
            "before": _count_items(original.get("campaigns") or original_summary.get("campaigns")),
            "after": _count_items(compacted.get("campaigns") or compacted_summary.get("campaigns")),
            "rule": "selected campaign or first 10 campaigns when compact context is enabled",
        },
        {
            "section": "serverContext.searchQueryInsights",
            "before": _count_items(original_search),
            "after": _count_items(compacted_search),
            "rule": f"top {search_query_limit} search queries" if search_query_limit else "no search query limit",
        },
        {
            "section": "chat.toolResults",
            "before": "full tool JSON",
            "after": "summary only" if tool_results_mode != "full" else "full tool JSON",
            "rule": f"tool_results_mode={tool_results_mode}",
        },
        {
            "section": "selectedCampaign",
            "before": "whole account",
            "after": selected_campaign_name or "whole account",
            "rule": "focus prompt on selected campaign when provided",
        },
    ]


def _build_request_trace(
    *,
    client_id: str,
    user_message: str,
    selected_model: str | None,
    max_tokens: int,
    ai_preset: str | None,
    history: list[AiChatMessage],
    traces: list[AiToolTrace],
    original_context: dict[str, Any] | None,
    compacted_context: dict[str, Any] | None,
    compact_prompt_context: dict[str, Any] | None,
    intent_plan: dict[str, Any] | None,
    data_fetch: list[dict[str, Any]] | None,
    prompt: str | None,
    request_debug: dict[str, Any] | None,
    prompt_debug: dict[str, Any] | None,
    compact_context: bool,
    tool_results_mode: str,
    chat_history_limit: int | None,
    search_query_limit: int | None,
    selected_campaign_name: str | None,
    guard_blocked: bool = False,
    guard_reason: str | None = None,
    response_status: str = "success",
    error_code: str | None = None,
    error_message: str | None = None,
) -> dict[str, Any]:
    size = (prompt_debug or {}).get("size") or (request_debug or {}).get("size") or {}
    payload = (request_debug or {}).get("payload") or {}
    prompt_info = {
        "system": DEFAULT_SYSTEM_PROMPT,
        "user": prompt or "",
        "messages": (request_debug or {}).get("messages") or payload.get("messages") or [],
        "estimatedInputTokens": size.get("estimatedInputTokens"),
        "estimatedTotalTokens": size.get("estimatedTotalTokens"),
        "contextLimit": size.get("contextLimit"),
        "isTooLarge": size.get("isTooLarge", False),
    }
    trace = {
        "mode": "ai_chat",
        "clientId": client_id,
        "userMessage": user_message,
        "analysisPlan": intent_plan or detect_analysis_intent(user_message),
        "compactPromptContext": {
            "availableSections": sorted((compact_prompt_context or {}).keys()),
            "omittedSections": (compact_prompt_context or {}).get("omittedSections", []),
            "limitations": (compact_prompt_context or {}).get("limitations", []),
        },
        "omittedSections": (compact_prompt_context or {}).get("omittedSections", []),
        "dataFetch": data_fetch or [],
        "campaignDynamicsAnalysis": {
            "available": bool(((compact_prompt_context or {}).get("campaignDynamicsAnalysis") or {}).get("available")),
            "rows": ((((compact_prompt_context or {}).get("campaignDynamicsAnalysis") or {}).get("dataQuality") or {}).get("rows", 0)),
            "campaigns": ((((compact_prompt_context or {}).get("campaignDynamicsAnalysis") or {}).get("dataQuality") or {}).get("campaigns", 0)),
            "windows": list(((((compact_prompt_context or {}).get("campaignDynamicsAnalysis") or {}).get("period") or {}).get("windows") or {}).keys()),
            "worstCampaignsCount": len((((compact_prompt_context or {}).get("campaignDynamicsAnalysis") or {}).get("worstCampaigns") or [])),
            "bestCampaignsCount": len((((compact_prompt_context or {}).get("campaignDynamicsAnalysis") or {}).get("bestCampaigns") or [])),
            "missingData": (((compact_prompt_context or {}).get("campaignDynamicsAnalysis") or {}).get("missingData") or []),
        },
        "selectedCampaignName": selected_campaign_name,
        "modelSettings": {
            "model": selected_model,
            "max_tokens": max_tokens,
            "temperature": payload.get("temperature", 0.2),
            "ai_preset": ai_preset,
            "compact_context": compact_context,
            "tool_results_mode": tool_results_mode,
            "chat_history_limit": chat_history_limit,
            "search_query_limit": search_query_limit,
        },
        "contextAssembly": {
            "source": "server-side trusted DirectPilot context",
            "client": _context_client_summary(compacted_context or original_context),
            "campaignSelection": {
                "mode": "selected_campaign" if selected_campaign_name else "whole_account",
                "selectedCampaignName": selected_campaign_name,
            },
            "compaction": _build_compaction_trace(
                original_context=original_context,
                compacted_context=compacted_context,
                history=history,
                chat_history_limit=chat_history_limit,
                tool_results_mode=tool_results_mode,
                search_query_limit=search_query_limit,
                selected_campaign_name=selected_campaign_name,
            ),
        },
        "tools": [_tool_trace_entry(trace, tool_results_mode=tool_results_mode) for trace in traces],
        "prompt": prompt_info,
        "openrouterPayload": payload,
        "guard": {"blocked": guard_blocked, "reason": guard_reason},
        "response": {
            "status": response_status,
            "errorCode": error_code,
            "errorMessage": error_message,
        },
    }
    return redact_openrouter_debug_payload(trace)


def build_chat_prompt_debug_snapshot(
    *,
    client_id: str,
    message: str,
    model: str,
    history: list[AiChatMessage],
    client_context: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    include_preview: bool = False,
    display_message: str | None = None,
    compact_context: bool = True,
    tool_results_mode: str = "summary",
    chat_history_limit: int | None = 3,
    search_query_limit: int | None = 20,
    selected_campaign_name: str | None = None,
) -> dict[str, Any]:
    compacted_context = compact_client_context_for_chat(
        client_context,
        compact_context=compact_context,
        search_query_limit=search_query_limit,
        selected_campaign_name=selected_campaign_name,
    )
    intent_plan = detect_analysis_intent(display_message or message)
    compact_prompt_context = build_compact_ai_chat_context(
        compacted_context,
        intent_plan,
        {"search_query_limit": search_query_limit},
    )
    data_fetch = _build_data_fetch_trace(compact_prompt_context)
    traces = _run_mcp_tools(client_id, message, client_context=compact_prompt_context)
    prompt = _build_chat_prompt(
        client_id=client_id,
        message=message,
        history=history,
        traces=traces,
        compact_prompt_context=compact_prompt_context,
        intent_plan=intent_plan,
        tool_results_mode=tool_results_mode,
        chat_history_limit=chat_history_limit,
    )
    snapshot = build_prompt_debug_snapshot(
        context=_build_chat_debug_context(
            client_id=client_id,
            message=message,
            history=history,
            traces=traces,
            client_context=compact_prompt_context,
            display_message=display_message,
            tool_results_mode=tool_results_mode,
            chat_history_limit=chat_history_limit,
        ),
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt=prompt,
        model=model,
        max_tokens=max_tokens or 900,
        include_preview=include_preview,
    )
    snapshot["openrouterRequestPreview"] = build_openrouter_request_debug(
        mode="chat",
        endpoint="/api/v1/clients/{client_id}/ai/prompt-debug?mode=chat",
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt=prompt,
        model=model,
        max_tokens=max_tokens or 900,
        context=_build_chat_debug_context(
            client_id=client_id,
            message=message,
            history=history,
            traces=traces,
            client_context=compact_prompt_context,
            display_message=display_message,
            tool_results_mode=tool_results_mode,
            chat_history_limit=chat_history_limit,
        ),
        compact_options={
            "compact_context": compact_context,
            "tool_results_mode": tool_results_mode,
            "chat_history_limit": chat_history_limit,
            "search_query_limit": search_query_limit,
            "selected_campaign_name": selected_campaign_name,
        },
        include_preview=True,
    )
    snapshot["requestTracePreview"] = _build_request_trace(
        client_id=client_id,
        user_message=display_message or message,
        selected_model=model,
        max_tokens=max_tokens or 900,
        ai_preset=None,
        history=history,
        traces=traces,
        original_context=client_context,
        compacted_context=compacted_context,
        compact_prompt_context=compact_prompt_context,
        intent_plan=intent_plan,
        data_fetch=data_fetch,
        prompt=prompt,
        request_debug=snapshot["openrouterRequestPreview"],
        prompt_debug=snapshot,
        compact_context=compact_context,
        tool_results_mode=tool_results_mode,
        chat_history_limit=chat_history_limit,
        search_query_limit=search_query_limit,
        selected_campaign_name=selected_campaign_name,
        response_status="preview",
    )
    return {**snapshot, "mode": "chat", "toolTraceCount": len(traces)}


def _fallback_answer(client_id: str, message: str, traces: list[AiToolTrace]) -> str:
    campaign_trace = next((trace for trace in traces if trace.name in {"list_campaigns", "list_yandex_direct_campaigns"}), None)
    audit_trace = next((trace for trace in traces if trace.name == "list_audit_issues"), None)
    goals_trace = next((trace for trace in traces if trace.name == "list_yandex_metrica_goals"), None)
    campaigns = campaign_trace.result if campaign_trace else []
    audits = audit_trace.result if audit_trace else []
    goals = goals_trace.result if goals_trace else []

    first_problem_campaign = campaigns[1] if isinstance(campaigns, list) and len(campaigns) > 1 else None
    top_audit = audits[0] if isinstance(audits, list) and audits else None

    lines = [
        "OpenRouter сейчас не настроен, поэтому отвечаю детерминированно по MCP-контексту.",
        "",
        "**Что вижу по данным:**",
    ]
    if first_problem_campaign:
        lines.append(
            f"- В Директе выделяется кампания «{first_problem_campaign.get('name')}»: расход {first_problem_campaign.get('spend')}, лиды {first_problem_campaign.get('leads')}, CPA {first_problem_campaign.get('cpa')}."
        )
    if top_audit:
        lines.append(f"- Главный audit issue: {top_audit.get('title')} — {top_audit.get('evidence')}")
    if goals:
        lines.append(f"- По Метрике доступна цель «{goals[0].get('name')}» для counter_id {goals[0].get('counter_id')}.")
    else:
        lines.append("- Цели Метрики пока не подтверждены реальным connector-ом, поэтому выводы по CPA нужно проверять осторожно.")

    lines.extend(
        [
            "",
            "**Что сделать дальше:**",
            "1. Проверить связку кампаний с целями Метрики и корректность конверсий.",
            "2. Создать dry-run preview по ограничению расхода без конверсий, без автоматического применения.",
            "3. После проверки evidence отправить изменение на approval специалисту или клиенту.",
            "",
            f"Вопрос пользователя был: «{message}». Клиент: {client_id}.",
        ]
    )
    return "\n".join(lines)


async def answer_ai_chat(
    client_id: str,
    message: str,
    model: str | None,
    history: list[AiChatMessage],
    client_context: dict[str, Any] | None = None,
    max_tokens: int | None = None,
    compact_context: bool = True,
    tool_results_mode: str = "summary",
    chat_history_limit: int | None = 3,
    search_query_limit: int | None = 20,
    selected_campaign_name: str | None = None,
    inspect_request: bool = False,
) -> AiChatResponse:
    selected_model = model or settings.openrouter_default_model
    safe_max_tokens = max_tokens or 900
    compacted_context = compact_client_context_for_chat(
        client_context,
        compact_context=compact_context,
        search_query_limit=search_query_limit,
        selected_campaign_name=selected_campaign_name,
    )
    intent_plan = detect_analysis_intent(message)
    compact_prompt_context = build_compact_ai_chat_context(
        compacted_context,
        intent_plan,
        {"search_query_limit": search_query_limit},
    )
    data_fetch = _build_data_fetch_trace(compact_prompt_context)
    traces = _run_mcp_tools(client_id, message, client_context=compact_prompt_context)
    prompt = _build_chat_prompt(
        client_id=client_id,
        message=message,
        history=history,
        traces=traces,
        compact_prompt_context=compact_prompt_context,
        intent_plan=intent_plan,
        tool_results_mode=tool_results_mode,
        chat_history_limit=chat_history_limit,
    )
    prompt_debug = build_prompt_debug_snapshot(
        context=_build_chat_debug_context(
            client_id=client_id,
            message=message,
            history=history,
            traces=traces,
            client_context=compact_prompt_context,
            tool_results_mode=tool_results_mode,
            chat_history_limit=chat_history_limit,
        ),
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt=prompt,
        model=selected_model,
        max_tokens=safe_max_tokens,
        include_preview=False,
    )
    request_debug = build_openrouter_request_debug(
        mode="chat",
        endpoint="/api/v1/ai/chat",
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt=prompt,
        model=selected_model,
        max_tokens=safe_max_tokens,
        context=_build_chat_debug_context(
            client_id=client_id,
            message=message,
            history=history,
            traces=traces,
            client_context=compact_prompt_context,
            tool_results_mode=tool_results_mode,
            chat_history_limit=chat_history_limit,
        ),
        compact_options={
            "compact_context": compact_context,
            "tool_results_mode": tool_results_mode,
            "chat_history_limit": chat_history_limit,
            "search_query_limit": search_query_limit,
            "selected_campaign_name": selected_campaign_name,
        },
        include_preview=True,
    )
    base_trace_kwargs = {
        "client_id": client_id,
        "user_message": message,
        "selected_model": selected_model,
        "max_tokens": safe_max_tokens,
        "ai_preset": None,
        "history": history,
        "traces": traces,
        "original_context": client_context,
        "compacted_context": compacted_context,
        "compact_prompt_context": compact_prompt_context,
        "intent_plan": intent_plan,
        "data_fetch": data_fetch,
        "prompt": prompt,
        "request_debug": request_debug,
        "prompt_debug": prompt_debug,
        "compact_context": compact_context,
        "tool_results_mode": tool_results_mode,
        "chat_history_limit": chat_history_limit,
        "search_query_limit": search_query_limit,
        "selected_campaign_name": selected_campaign_name,
    }

    if not settings.openrouter_configured:
        return AiChatResponse(
            client_id=client_id,
            model=None,
            source="mcp_deterministic_fallback",
            answer=_fallback_answer(client_id, message, traces),
            tool_traces=traces,
            requestTrace=_build_request_trace(
                **{**base_trace_kwargs, "selected_model": None},
                response_status="fallback",
            ),
        )

    if prompt_debug["size"]["isTooLarge"]:
        return AiChatResponse(
            client_id=client_id,
            model=selected_model,
            source="prompt_budget_guard",
            answer=(
                "Контекст AI-чата слишком большой для выбранной модели. Выберите конкретную кампанию, "
                "очистите историю чата или используйте сжатый контекст."
            ),
            tool_traces=traces,
            error=True,
            error_code="ai_prompt_too_large",
            message=(
                "Контекст AI-чата слишком большой для выбранной модели. Выберите конкретную кампанию, "
                "очистите историю чата или используйте сжатый контекст."
            ),
            retryable=False,
            requestDebug=request_debug,
            requestTrace=_build_request_trace(
                **base_trace_kwargs,
                guard_blocked=True,
                guard_reason="ai_prompt_too_large",
                response_status="blocked",
                error_code="ai_prompt_too_large",
            ),
        )
    try:
        response = await generate_openrouter_response(
            model=selected_model,
            prompt=prompt,
            max_tokens=safe_max_tokens,
        )
    except HTTPException as exc:
        detail_text = json.dumps(exc.detail, ensure_ascii=False) if isinstance(exc.detail, (dict, list)) else str(exc.detail)
        is_rate_limited = (
            exc.status_code == 429
            or "429" in detail_text
            or "rate limit" in detail_text.lower()
            or "rate-limited" in detail_text.lower()
            or "temporarily rate" in detail_text.lower()
        )
        error_code = "openrouter_rate_limited" if is_rate_limited else "openrouter_error"
        message_text = (
            "Р’С‹Р±СЂР°РЅРЅР°СЏ AI-РјРѕРґРµР»СЊ РІСЂРµРјРµРЅРЅРѕ РїРµСЂРµРіСЂСѓР¶РµРЅР° РёР»Рё РѕРіСЂР°РЅРёС‡РµРЅР° РїРѕ Р»РёРјРёС‚Р°Рј. Р’С‹Р±РµСЂРёС‚Рµ РґСЂСѓРіСѓСЋ РјРѕРґРµР»СЊ РёР»Рё РїРѕРІС‚РѕСЂРёС‚Рµ РїРѕР·Р¶Рµ."
            if is_rate_limited
            else "OpenRouter РЅРµ РІРµСЂРЅСѓР» РѕС‚РІРµС‚ РґР»СЏ AI-С‡Р°С‚Р°."
        )
        return AiChatResponse(
            client_id=client_id,
            model=selected_model,
            source="openrouter_error_normalized",
            answer=message_text,
            tool_traces=traces,
            error=True,
            error_code=error_code,
            message=message_text,
            retryable=is_rate_limited,
            suggested_preset="economy" if is_rate_limited else None,
            requestDebug=request_debug if inspect_request else None,
            requestTrace=_build_request_trace(
                **base_trace_kwargs,
                response_status="error",
                error_code=error_code,
                error_message=message_text,
            ),
        )
    return AiChatResponse(
        client_id=client_id,
        model=str(response.get("model") or selected_model),
        source="openrouter_with_mcp_tools",
        answer=str(response.get("content") or "Модель не вернула текстовый ответ."),
        tool_traces=traces,
        requestDebug=request_debug if inspect_request else None,
        requestTrace=_build_request_trace(**base_trace_kwargs),
    )
