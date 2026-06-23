import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_session_user
from app.core.config import (
    AI_MODEL_PRESETS,
    AI_RECOMMENDED_DEFAULT_PRESET,
    ai_model_cost_tier,
    ai_model_label,
    ai_model_recommended_for,
    ai_recommended_default_model,
    normalize_ai_request_options,
    settings,
)
from app.db import get_optional_db
from app.models import ClientAccount
from app.schemas import AiChatRequest, AiChatResponse, AiPromptRequest, AiPromptResponse, AiStatusResponse
from app.services.ai_chat import answer_ai_chat, build_enriched_chat_message, compact_client_context_for_chat
from app.services.ai_recommendations import build_client_ai_context_from_db
from app.services.openrouter import generate_openrouter_response, openrouter_status

router = APIRouter(prefix="/ai", tags=["ai"])

AI_RATE_LIMIT_MESSAGE = "Выбранная AI-модель временно перегружена или ограничена по лимитам. Выберите другую модель или повторите позже."


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
    recommended_model = ai_recommended_default_model(settings.openrouter_models, settings.openrouter_default_model)
    presets = [
        {
            **preset,
            "default_model": recommended_model if preset_id == "economy" else settings.openrouter_default_model,
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
        models=settings.openrouter_models,
        configured_default=settings.openrouter_default_model,
    )


def _is_rate_limit_error(exc: HTTPException) -> bool:
    detail = exc.detail
    text = json.dumps(detail, ensure_ascii=False).lower() if isinstance(detail, (dict, list)) else str(detail).lower()
    return exc.status_code == 429 or "429" in text or "rate limit" in text or "rate-limited" in text or "temporarily rate" in text


def _normalized_ai_error(exc: HTTPException, model: str) -> dict[str, object] | None:
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
    try:
        return await generate_openrouter_response(
            model=selected_model,
            prompt=prompt,
            max_tokens=int(ai_options["max_tokens"]),
        )
    except HTTPException as exc:
        normalized = _normalized_ai_error(exc, selected_model)
        if normalized:
            return {"content": "", **normalized}
        raise


@router.post("/chat", response_model=AiChatResponse)
async def chat_with_ai(
    payload: AiChatRequest,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> AiChatResponse:
    ai_options = _resolved_ai_options(payload.model, payload.ai_preset, payload.max_tokens)
    server_context = payload.client_context
    if db is not None:
        client = db.get(ClientAccount, payload.client_id)
        if not client or client.organization_id != current.organization.id:
            raise HTTPException(status_code=404, detail="Client not found")
        server_context = build_client_ai_context_from_db(db, payload.client_id, selected_campaign_name=payload.selected_campaign_name)
    compacted_context = compact_client_context_for_chat(
        server_context,
        compact_context=payload.compact_context,
        search_query_limit=payload.search_query_limit,
        selected_campaign_name=payload.selected_campaign_name,
    )
    enriched_message = payload.message
    if compacted_context:
        enriched_message = build_enriched_chat_message(payload.message, compacted_context, ai_options)
    selected_model = str(ai_options["model"])
    try:
        return await answer_ai_chat(
            client_id=payload.client_id,
            message=enriched_message,
            model=selected_model,
            history=payload.history,
            client_context=compacted_context,
            max_tokens=int(ai_options["max_tokens"]),
            compact_context=payload.compact_context,
            tool_results_mode=payload.tool_results_mode,
            chat_history_limit=payload.chat_history_limit,
            search_query_limit=payload.search_query_limit,
            selected_campaign_name=payload.selected_campaign_name,
        )
    except HTTPException as exc:
        normalized = _normalized_ai_error(exc, selected_model)
        if normalized:
            return AiChatResponse(
                client_id=payload.client_id,
                model=selected_model,
                source="openrouter_error_normalized",
                answer=str(normalized["message"]),
                tool_traces=[],
                **normalized,
            )
        raise
