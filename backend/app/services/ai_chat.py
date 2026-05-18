import json
from typing import Any

from app.core.config import settings
from app.mcp.tools import call_tool
from app.schemas import AiChatMessage, AiChatResponse, AiToolTrace
from app.services.openrouter import generate_openrouter_response

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


def _run_mcp_tools(client_id: str, message: str) -> list[AiToolTrace]:
    traces: list[AiToolTrace] = []
    for name, args_factory in _select_mcp_tools(message):
        arguments = args_factory(client_id)
        result = call_tool(name, arguments)
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


async def answer_ai_chat(client_id: str, message: str, model: str | None, history: list[AiChatMessage]) -> AiChatResponse:
    traces = _run_mcp_tools(client_id, message)
    if not settings.openrouter_configured:
        return AiChatResponse(
            client_id=client_id,
            model=None,
            source="mcp_deterministic_fallback",
            answer=_fallback_answer(client_id, message, traces),
            tool_traces=traces,
        )

    selected_model = model or settings.openrouter_default_model
    response = await generate_openrouter_response(
        model=selected_model,
        prompt=_build_chat_prompt(client_id=client_id, message=message, history=history, traces=traces),
    )
    return AiChatResponse(
        client_id=client_id,
        model=str(response.get("model") or selected_model),
        source="openrouter_with_mcp_tools",
        answer=str(response.get("content") or "Модель не вернула текстовый ответ."),
        tool_traces=traces,
    )
