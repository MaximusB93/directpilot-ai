from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_session_user
from app.db import get_optional_db
from app.models import ClientAccount
from app.schemas import AiChatRequest, AiChatResponse, AiPromptRequest, AiPromptResponse, AiStatusResponse
from app.services.ai_chat import answer_ai_chat
from app.services.openrouter import generate_openrouter_response, openrouter_status

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/openrouter/status", response_model=AiStatusResponse)
def get_openrouter_status() -> dict[str, object]:
    return openrouter_status()


@router.post("/openrouter/generate", response_model=AiPromptResponse)
async def generate_ai_response(
    payload: AiPromptRequest,
    current: CurrentUser = Depends(get_current_session_user),
) -> dict[str, object]:
    return await generate_openrouter_response(model=payload.model, prompt=payload.prompt)


@router.post("/chat", response_model=AiChatResponse)
async def chat_with_ai(
    payload: AiChatRequest,
    db: Session | None = Depends(get_optional_db),
    current: CurrentUser = Depends(get_current_session_user),
) -> AiChatResponse:
    if db is not None:
        client = db.get(ClientAccount, payload.client_id)
        if not client or client.organization_id != current.organization.id:
            raise HTTPException(status_code=404, detail="Client not found")
    return await answer_ai_chat(
        client_id=payload.client_id,
        message=payload.message,
        model=payload.model,
        history=payload.history,
        client_context=payload.client_context,
    )
