from app.schemas import ApprovalCreateRequest, ApprovalDecisionRequest
from app.services import approvals


def test_preview_contains_policy_fields() -> None:
    preview = approvals.create_preview("pause-wasted-keywords", client_id="furniture", actor="test")
    assert preview.id.startswith("preview_")
    assert isinstance(preview.risk_score, int)
    assert preview.risk_score >= 0
    assert isinstance(preview.policy_violations, list)


def test_high_risk_requires_lead_or_owner() -> None:
    preview = approvals.create_preview("pause-wasted-keywords", client_id="furniture", actor="test")
    forced = preview.model_copy(update={"risk_score": 80})
    approvals._PREVIEWS[preview.id] = forced  # noqa: SLF001

    approval = approvals.create_approval(
        ApprovalCreateRequest(preview_id=preview.id, requested_by="spec", requested_by_role="specialist")
    )

    try:
        approvals.approve_approval(
            approval.id,
            ApprovalDecisionRequest(decided_by="junior", decided_by_role="specialist", comment="approve"),
        )
        assert False, "Expected ValueError for high-risk approval by specialist"
    except ValueError as exc:
        assert "High-risk approval requires lead or owner role" in str(exc)


def test_lead_can_approve_high_risk() -> None:
    preview = approvals.create_preview("pause-wasted-keywords", client_id="furniture", actor="test")
    forced = preview.model_copy(update={"risk_score": 80})
    approvals._PREVIEWS[preview.id] = forced  # noqa: SLF001

    approval = approvals.create_approval(
        ApprovalCreateRequest(preview_id=preview.id, requested_by="spec", requested_by_role="specialist")
    )
    result = approvals.approve_approval(
        approval.id,
        ApprovalDecisionRequest(decided_by="lead-user", decided_by_role="lead", comment="ok"),
    )
    assert result.status == "approved"
    assert result.decided_by == "lead-user"
