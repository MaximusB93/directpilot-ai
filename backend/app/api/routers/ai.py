from fastapi import APIRouter

from app.schemas import AiPromptRequest, AiPromptResponse, AiStatusResponse
from app.services.openrouter import generate_openrouter_response, openrouter_status

router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/openrouter/status", response_model=AiStatusResponse)
def get_openrouter_status() -> dict[str, object]:
    return openrouter_status()


@router.post("/openrouter/generate", response_model=AiPromptResponse)
async def generate_ai_response(payload: AiPromptRequest) -> dict[str, object]:
    return await generate_openrouter_response(model=payload.model, prompt=payload.prompt)
