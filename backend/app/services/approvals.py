import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models_workflow import AuditLogRecord, RecommendationApproval, RecommendationPreview
from app.schemas import ApprovalCreateRequest, ApprovalDecisionRequest, ApprovalRecord, AuditLogEvent, ChangePreview, PlannedChange
from app.services.mock_data import CLIENTS, RECOMMENDATIONS
from app.services.policy_engine import evaluate_preview

_PREVIEWS: dict[str, ChangePreview] = {}
_APPROVALS: dict[str, ApprovalRecord] = {}
_AUDIT_LOG: list[AuditLogEvent] = []


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _find_client(client_id: str):
    for client in CLIENTS:
        if client.id == client_id:
            return client
    raise ValueError(f"Client '{client_id}' was not found")


def _find_recommendation(recommendation_id: str):
    for recommendation in RECOMMENDATIONS:
        if recommendation.id == recommendation_id:
            return recommendation
    raise ValueError(f"Recommendation '{recommendation_id}' was not found")


def _append_event(db: Session | None, event_type: str, actor: str, description: str, entity_id: str | None = None) -> AuditLogEvent:
    event = AuditLogEvent(id=f"evt_{len(_AUDIT_LOG) + 1:04d}", type=event_type, actor=actor, description=description, created_at=_now(), entity_id=entity_id)
    _AUDIT_LOG.append(event)
    if db is not None:
        db.add(AuditLogRecord(event_type=event_type, actor=actor, description=description, entity_id=entity_id))
        db.commit()
    return event


def create_preview(recommendation_id: str, client_id: str = "furniture", actor: str = "ai-agent", db: Session | None = None) -> ChangePreview:
    _find_client(client_id)
    recommendation = _find_recommendation(recommendation_id)
    preview_id = f"preview_{recommendation_id}_{client_id}"
    changes = [PlannedChange(object_type=item.type, object_name=item.name, campaign=item.campaign, before=recommendation.diff.before, after=recommendation.diff.after, action=item.action) for item in recommendation.affected_items]
    preview = ChangePreview(id=preview_id, recommendation_id=recommendation.id, client_id=client_id, risk=recommendation.risk, requires_approval=True, summary=f"Dry-run: {recommendation.title}. Planned changes: {len(changes)}.", changes=changes)
    verdict = evaluate_preview(preview)
    preview = preview.model_copy(update={"policy_violations": verdict.violations, "risk_score": verdict.risk_score})
    _PREVIEWS[preview.id] = preview
    if db is not None:
        db.merge(RecommendationPreview(
            id=preview.id,
            recommendation_id=preview.recommendation_id,
            client_id=preview.client_id,
            risk=preview.risk,
            requires_approval=1 if preview.requires_approval else 0,
            summary=preview.summary,
            payload_json=preview.model_dump_json(),
            policy_violations_json=json.dumps(preview.policy_violations, ensure_ascii=False),
            risk_score=preview.risk_score,
        ))
        db.commit()
    _append_event(db, "preview_created", actor, f"Created dry-run preview for {recommendation.id}", preview.id)
    return preview


def get_preview(preview_id: str, db: Session | None = None) -> ChangePreview:
    if preview_id in _PREVIEWS:
        return _PREVIEWS[preview_id]
    if db is not None:
        row = db.get(RecommendationPreview, preview_id)
        if row:
            return ChangePreview.model_validate_json(row.payload_json)
    raise ValueError(f"Preview '{preview_id}' was not found")


def create_approval(request: ApprovalCreateRequest, db: Session | None = None) -> ApprovalRecord:
    preview = get_preview(request.preview_id, db=db)
    approval = ApprovalRecord(
        id=f"approval_{len(_APPROVALS) + 1:04d}",
        preview_id=preview.id,
        recommendation_id=preview.recommendation_id,
        client_id=preview.client_id,
        requested_by=request.requested_by,
        requested_by_role=request.requested_by_role,
        status="pending",
        created_at=_now(),
        policy_violations=preview.policy_violations,
        risk_score=preview.risk_score,
    )
    _APPROVALS[approval.id] = approval
    if db is not None:
        db.merge(RecommendationApproval(
            id=approval.id,
            preview_id=approval.preview_id,
            recommendation_id=approval.recommendation_id,
            client_id=approval.client_id,
            requested_by=approval.requested_by,
            requested_by_role=approval.requested_by_role,
            status=approval.status,
            policy_violations_json=json.dumps(approval.policy_violations, ensure_ascii=False),
            risk_score=approval.risk_score,
        ))
        db.commit()
    _append_event(db, "approval_requested", request.requested_by, f"Requested approval for preview {preview.id}", approval.id)
    return approval


def _decide_approval(approval_id: str, request: ApprovalDecisionRequest, status: str, db: Session | None = None) -> ApprovalRecord:
    approval = _APPROVALS.get(approval_id)
    if approval is None and db is not None:
        row = db.get(RecommendationApproval, approval_id)
        if row:
            approval = ApprovalRecord(
                id=row.id, preview_id=row.preview_id, recommendation_id=row.recommendation_id, client_id=row.client_id,
                requested_by=row.requested_by, requested_by_role=row.requested_by_role, status=row.status,
                created_at=row.created_at.isoformat(), policy_violations=json.loads(row.policy_violations_json or "[]"),
                risk_score=row.risk_score, decided_by=row.decided_by, decided_at=row.decided_at.isoformat() if row.decided_at else None,
                comment=row.comment,
            )
    if approval is None:
        raise ValueError(f"Approval '{approval_id}' was not found")
    if approval.status != "pending":
        raise ValueError(f"Approval '{approval_id}' is already {approval.status}")
    if status == "approved" and approval.risk_score >= 70 and request.decided_by_role not in {"lead", "owner"}:
        raise ValueError("High-risk approval requires lead or owner role")

    updated = approval.model_copy(update={"status": status, "decided_by": request.decided_by, "decided_at": _now(), "comment": request.comment})
    _APPROVALS[approval_id] = updated
    if db is not None:
        row = db.get(RecommendationApproval, approval_id)
        if row:
            row.status = status
            row.decided_by = request.decided_by
            row.decided_at = datetime.now(UTC)
            row.comment = request.comment
            db.commit()
    _append_event(db, f"approval_{status}", request.decided_by, f"Approval {approval_id} marked as {status}", approval_id)
    return updated


def approve_approval(approval_id: str, request: ApprovalDecisionRequest, db: Session | None = None) -> ApprovalRecord:
    return _decide_approval(approval_id, request, "approved", db=db)


def reject_approval(approval_id: str, request: ApprovalDecisionRequest, db: Session | None = None) -> ApprovalRecord:
    return _decide_approval(approval_id, request, "rejected", db=db)


def list_approvals(db: Session | None = None) -> list[ApprovalRecord]:
    if db is None:
        return list(_APPROVALS.values())
    rows = db.scalars(select(RecommendationApproval).order_by(RecommendationApproval.created_at.desc())).all()
    return [ApprovalRecord(id=r.id, preview_id=r.preview_id, recommendation_id=r.recommendation_id, client_id=r.client_id, requested_by=r.requested_by, requested_by_role=r.requested_by_role, status=r.status, created_at=r.created_at.isoformat(), policy_violations=json.loads(r.policy_violations_json or "[]"), risk_score=r.risk_score, decided_by=r.decided_by, decided_at=r.decided_at.isoformat() if r.decided_at else None, comment=r.comment) for r in rows]


def list_audit_log(db: Session | None = None) -> list[AuditLogEvent]:
    if db is None:
        return _AUDIT_LOG
    rows = db.scalars(select(AuditLogRecord).order_by(AuditLogRecord.created_at.desc())).all()
    return [AuditLogEvent(id=r.id, type=r.event_type, actor=r.actor, description=r.description, created_at=r.created_at.isoformat(), entity_id=r.entity_id) for r in rows]
