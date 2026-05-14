from datetime import UTC, datetime

from app.schemas import (
    ApprovalCreateRequest,
    ApprovalDecisionRequest,
    ApprovalRecord,
    AuditLogEvent,
    ChangePreview,
    PlannedChange,
)
from app.services.mock_data import CLIENTS, RECOMMENDATIONS

_PREVIEWS: dict[str, ChangePreview] = {}
_APPROVALS: dict[str, ApprovalRecord] = {}
_AUDIT_LOG: list[AuditLogEvent] = []


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _append_event(event_type: str, actor: str, description: str, entity_id: str | None = None) -> AuditLogEvent:
    event = AuditLogEvent(
        id=f"evt_{len(_AUDIT_LOG) + 1:04d}",
        type=event_type,
        actor=actor,
        description=description,
        created_at=_now(),
        entity_id=entity_id,
    )
    _AUDIT_LOG.append(event)
    return event


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


def create_preview(recommendation_id: str, client_id: str = "furniture", actor: str = "ai-agent") -> ChangePreview:
    _find_client(client_id)
    recommendation = _find_recommendation(recommendation_id)
    preview_id = f"preview_{recommendation_id}_{client_id}"

    changes = [
        PlannedChange(
            object_type=item.type,
            object_name=item.name,
            campaign=item.campaign,
            before=recommendation.diff.before,
            after=recommendation.diff.after,
            action=item.action,
        )
        for item in recommendation.affected_items
    ]

    preview = ChangePreview(
        id=preview_id,
        recommendation_id=recommendation.id,
        client_id=client_id,
        risk=recommendation.risk,
        requires_approval=True,
        summary=f"Dry-run: {recommendation.title}. Planned changes: {len(changes)}.",
        changes=changes,
    )
    _PREVIEWS[preview.id] = preview
    _append_event("preview_created", actor, f"Created dry-run preview for {recommendation.id}", preview.id)
    return preview


def get_preview(preview_id: str) -> ChangePreview:
    try:
        return _PREVIEWS[preview_id]
    except KeyError as exc:
        raise ValueError(f"Preview '{preview_id}' was not found") from exc


def create_approval(request: ApprovalCreateRequest) -> ApprovalRecord:
    preview = get_preview(request.preview_id)
    approval = ApprovalRecord(
        id=f"approval_{len(_APPROVALS) + 1:04d}",
        preview_id=preview.id,
        recommendation_id=preview.recommendation_id,
        client_id=preview.client_id,
        requested_by=request.requested_by,
        status="pending",
        created_at=_now(),
    )
    _APPROVALS[approval.id] = approval
    _append_event(
        "approval_requested",
        request.requested_by,
        f"Requested approval for preview {preview.id}",
        approval.id,
    )
    return approval


def _decide_approval(approval_id: str, request: ApprovalDecisionRequest, status: str) -> ApprovalRecord:
    try:
        approval = _APPROVALS[approval_id]
    except KeyError as exc:
        raise ValueError(f"Approval '{approval_id}' was not found") from exc

    if approval.status != "pending":
        raise ValueError(f"Approval '{approval_id}' is already {approval.status}")

    updated = approval.model_copy(
        update={
            "status": status,
            "decided_by": request.decided_by,
            "decided_at": _now(),
            "comment": request.comment,
        }
    )
    _APPROVALS[approval_id] = updated
    _append_event(
        f"approval_{status}",
        request.decided_by,
        f"Approval {approval_id} marked as {status}",
        approval_id,
    )
    return updated


def approve_approval(approval_id: str, request: ApprovalDecisionRequest) -> ApprovalRecord:
    return _decide_approval(approval_id, request, "approved")


def reject_approval(approval_id: str, request: ApprovalDecisionRequest) -> ApprovalRecord:
    return _decide_approval(approval_id, request, "rejected")


def list_approvals() -> list[ApprovalRecord]:
    return list(_APPROVALS.values())


def list_audit_log() -> list[AuditLogEvent]:
    return _AUDIT_LOG
