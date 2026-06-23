import json
from typing import Any

from app.core.config import settings
from app.mcp.tools import call_tool
from app.schemas import AiChatMessage, AiChatResponse, AiToolTrace
from app.services.ai_prompt_debug import build_prompt_debug_snapshot
from app.services.direct_analyst_playbook import build_direct_analyst_instructions
from app.services.openrouter import DEFAULT_SYSTEM_PROMPT, generate_openrouter_response

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
    return tool_plan


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


def _format_history(messages: list[AiChatMessage]) -> str:
    if not messages:
        return "Истории диалога пока нет."
    return "\n".join(f"{item.role}: {item.content}" for item in messages[-8:])


def _build_chat_prompt(client_id: str, message: str, history: list[AiChatMessage], traces: list[AiToolTrace]) -> str:
    tool_context = [trace.model_dump() for trace in traces]
    return f"""
Ты AI-аналитик DirectPilot AI внутри чата PPC-специалиста.
Отвечай по-русски, кратко и структурно. Используй только факты из MCP tool results ниже.
Если данных недостаточно, явно напиши, какие данные нужно подключить из Яндекс.Директа, Метрики или CRM.
Не применяй изменения и не говори, что изменения уже внесены: только аналитика, dry-run, рекомендации и approval.

client_id: {client_id}
История диалога:
{_format_history(history)}

Текущий вопрос пользователя:
{message}

MCP tool results:
{json.dumps(tool_context, ensure_ascii=False, indent=2)}
""".strip()


def build_enriched_chat_message(message: str, server_context: dict[str, Any] | None, ai_options: dict[str, Any]) -> str:
    if not server_context:
        return message
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
        "campaigns",
        "diagnostics",
        "optimization_plan",
        "saved_optimization_actions",
        "knowledge_snippets",
        "warnings",
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
) -> dict[str, Any]:
    playbook = build_direct_analyst_instructions(client_context or {}) if client_context else ""
    context: dict[str, Any] = {
        "chat.message": display_message or message,
        "chat.history": [item.model_dump() for item in history[-8:]],
        "chat.playbook": playbook,
        "chat.serverContext": _summarize_server_context_for_debug(client_context),
        "chat.toolResults": [trace.model_dump() for trace in traces],
        "chat.finalPromptWrapper": _build_chat_prompt_wrapper_context(client_id),
    }
    context.update(_build_server_context_debug_sections(client_context))
    return context


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
) -> dict[str, Any]:
    traces = _run_mcp_tools(client_id, message, client_context=client_context)
    prompt = _build_chat_prompt(client_id=client_id, message=message, history=history, traces=traces)
    snapshot = build_prompt_debug_snapshot(
        context=_build_chat_debug_context(
            client_id=client_id,
            message=message,
            history=history,
            traces=traces,
            client_context=client_context,
            display_message=display_message,
        ),
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt=prompt,
        model=model,
        max_tokens=max_tokens or 900,
        include_preview=include_preview,
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
) -> AiChatResponse:
    traces = _run_mcp_tools(client_id, message, client_context=client_context)
    if not settings.openrouter_configured:
        return AiChatResponse(
            client_id=client_id,
            model=None,
            source="mcp_deterministic_fallback",
            answer=_fallback_answer(client_id, message, traces),
            tool_traces=traces,
        )

    selected_model = model or settings.openrouter_default_model
    prompt = _build_chat_prompt(client_id=client_id, message=message, history=history, traces=traces)
    prompt_debug = build_prompt_debug_snapshot(
        context=_build_chat_debug_context(
            client_id=client_id,
            message=message,
            history=history,
            traces=traces,
            client_context=client_context,
        ),
        system_prompt=DEFAULT_SYSTEM_PROMPT,
        user_prompt=prompt,
        model=selected_model,
        max_tokens=max_tokens or 900,
        include_preview=False,
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
        )
    response = await generate_openrouter_response(
        model=selected_model,
        prompt=prompt,
        max_tokens=max_tokens,
    )
    return AiChatResponse(
        client_id=client_id,
        model=str(response.get("model") or selected_model),
        source="openrouter_with_mcp_tools",
        answer=str(response.get("content") or "Модель не вернула текстовый ответ."),
        tool_traces=traces,
    )
