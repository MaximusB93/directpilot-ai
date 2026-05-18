from fastapi import APIRouter

from app.schemas import AiChatRequest, AiChatResponse, AiPromptRequest, AiPromptResponse, AiStatusResponse
from app.services.ai_chat import answer_ai_chat
from app.services.openrouter import generate_openrouter_response, openrouter_status

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/openrouter/status", response_model=AiStatusResponse)
def get_openrouter_status() -> dict[str, object]:
    return openrouter_status()


@router.post("/openrouter/generate", response_model=AiPromptResponse)
async def generate_ai_response(payload: AiPromptRequest) -> dict[str, object]:
    return await generate_openrouter_response(model=payload.model, prompt=payload.prompt)


@router.post("/chat", response_model=AiChatResponse)
async def chat_with_ai(payload: AiChatRequest) -> AiChatResponse:
    return await answer_ai_chat(
        client_id=payload.client_id,
        message=payload.message,
        model=payload.model,
        history=payload.history,
        client_context=payload.client_context,
    )
