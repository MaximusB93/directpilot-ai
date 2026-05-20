from fastapi import APIRouter, Depends, HTTPException

from sqlalchemy.orm import Session

from app.db import get_optional_db
from app.schemas import (
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    ApprovalRecord,
    AuditLogEvent,
    ChangePreview,
    RecommendationImpactCreateRequest,
    RecommendationImpactEvent,
)
from app.services.approvals import (
    approve_approval,
    create_approval,
    create_preview,
    list_approvals,
    list_audit_log,
    reject_approval,
)
from app.services.impact_tracking import create_impact_event, list_impact_events

router = APIRouter(tags=["approvals"])


@router.post("/recommendations/{recommendation_id}/preview", response_model=ChangePreview)
def preview_recommendation(recommendation_id: str, client_id: str = "furniture", db: Session | None = Depends(get_optional_db)) -> ChangePreview:
    try:
        return create_preview(recommendation_id=recommendation_id, client_id=client_id, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/approvals", response_model=ApprovalRecord)
def request_approval(request: ApprovalCreateRequest, db: Session | None = Depends(get_optional_db)) -> ApprovalRecord:
    try:
        return create_approval(request, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/approvals", response_model=list[ApprovalRecord])
def get_approvals(db: Session | None = Depends(get_optional_db)) -> list[ApprovalRecord]:
    return list_approvals(db=db)


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRecord)
def approve(approval_id: str, request: ApprovalDecisionRequest, db: Session | None = Depends(get_optional_db)) -> ApprovalRecord:
    try:
        return approve_approval(approval_id, request, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRecord)
def reject(approval_id: str, request: ApprovalDecisionRequest, db: Session | None = Depends(get_optional_db)) -> ApprovalRecord:
    try:
        return reject_approval(approval_id, request, db=db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/audit-log", response_model=list[AuditLogEvent])
def get_audit_log(db: Session | None = Depends(get_optional_db)) -> list[AuditLogEvent]:
    return list_audit_log(db=db)


@router.post("/recommendations/impact", response_model=RecommendationImpactEvent)
def create_recommendation_impact(payload: RecommendationImpactCreateRequest, db: Session | None = Depends(get_optional_db)) -> RecommendationImpactEvent:
    return create_impact_event(
        recommendation_id=payload.recommendation_id,
        client_id=payload.client_id,
        expected_impact=payload.expected_impact,
        observed_impact=payload.observed_impact,
        window_days=payload.window_days,
        created_by=payload.created_by,
        db=db,
    )


@router.get("/recommendations/impact", response_model=list[RecommendationImpactEvent])
def get_recommendation_impact(client_id: str | None = None, db: Session | None = Depends(get_optional_db)) -> list[RecommendationImpactEvent]:
    return list_impact_events(client_id=client_id, db=db)
