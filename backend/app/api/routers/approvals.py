from fastapi import APIRouter, HTTPException

from app.schemas import ApprovalCreateRequest, ApprovalDecisionRequest, ApprovalRecord, AuditLogEvent, ChangePreview
from app.services.approvals import (
    approve_approval,
    create_approval,
    create_preview,
    list_approvals,
    list_audit_log,
    reject_approval,
)

router = APIRouter(tags=["approvals"])


@router.post("/recommendations/{recommendation_id}/preview", response_model=ChangePreview)
def preview_recommendation(recommendation_id: str, client_id: str = "furniture") -> ChangePreview:
    try:
        return create_preview(recommendation_id=recommendation_id, client_id=client_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/approvals", response_model=ApprovalRecord)
def request_approval(request: ApprovalCreateRequest) -> ApprovalRecord:
    try:
        return create_approval(request)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/approvals", response_model=list[ApprovalRecord])
def get_approvals() -> list[ApprovalRecord]:
    return list_approvals()


@router.post("/approvals/{approval_id}/approve", response_model=ApprovalRecord)
def approve(approval_id: str, request: ApprovalDecisionRequest) -> ApprovalRecord:
    try:
        return approve_approval(approval_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/approvals/{approval_id}/reject", response_model=ApprovalRecord)
def reject(approval_id: str, request: ApprovalDecisionRequest) -> ApprovalRecord:
    try:
        return reject_approval(approval_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/audit-log", response_model=list[AuditLogEvent])
def get_audit_log() -> list[AuditLogEvent]:
    return list_audit_log()
