from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import CurrentUser, get_current_session_user
from app.schemas import Recommendation
from app.services.mock_data import RECOMMENDATIONS

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.get("", response_model=list[Recommendation])
def list_recommendations(current: CurrentUser = Depends(get_current_session_user)) -> list[Recommendation]:
    return RECOMMENDATIONS


@router.get("/{recommendation_id}", response_model=Recommendation)
def get_recommendation(
    recommendation_id: str,
    current: CurrentUser = Depends(get_current_session_user),
) -> Recommendation:
    for recommendation in RECOMMENDATIONS:
        if recommendation.id == recommendation_id:
            return recommendation
    raise HTTPException(status_code=404, detail="Recommendation not found")
