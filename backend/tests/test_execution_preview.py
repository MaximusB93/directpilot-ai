from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import CurrentUser
from app.api.routers.clients import get_client_optimization_action_execution_preview
from app.db import Base
from app.models import ClientAccount, OptimizationActionDraft, Organization, User


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _current_user(org: Organization, user: User) -> CurrentUser:
    return CurrentUser(email=user.email or "user@example.com", user=user, organization=org)


def test_execution_preview_is_safe_for_owned_action() -> None:
    SessionLocal = _session_factory()

    with SessionLocal() as db:
        org = Organization(id="org-1", name="Workspace")
        user = User(id="user-1", organization_id="org-1", email="user@example.com", provider="email")
        client = ClientAccount(id="client-1", organization_id="org-1", name="Client 1", segment="Test")
        action = OptimizationActionDraft(
            id="action-1",
            organization_id="org-1",
            client_id="client-1",
            source="manual",
            status="approved",
            campaign_name="Search Campaign",
            issue="Расход без конверсий",
            evidence="Cost > 0 and conversions = 0",
            draft_action="Проверить остановку кампании",
            action_type="pause_campaign",
        )
        db.add_all([org, user, client, action])
        db.commit()

        preview = get_client_optimization_action_execution_preview(
            "client-1",
            "action-1",
            db=db,
            current=_current_user(org, user),
        )

        assert preview.can_apply is False
        assert preview.apply_enabled is False
        assert preview.action_type == "pause_campaign"
        assert any("Остановка кампании" in warning for warning in preview.warnings)
        assert any("Yandex Direct write API is not called" in check for check in preview.safety_checks)


def test_execution_preview_rejects_other_workspace_action() -> None:
    SessionLocal = _session_factory()

    with SessionLocal() as db:
        org_a = Organization(id="org-a", name="A")
        org_b = Organization(id="org-b", name="B")
        user_b = User(id="user-b", organization_id="org-b", email="b@example.com", provider="email")
        client_a = ClientAccount(id="client-a", organization_id="org-a", name="Client A", segment="Test")
        action = OptimizationActionDraft(
            id="action-a",
            organization_id="org-a",
            client_id="client-a",
            source="manual",
            status="approved",
            issue="Проверить кампанию",
            evidence="Evidence",
            draft_action="Manual review",
            action_type="manual_review",
        )
        db.add_all([org_a, org_b, user_b, client_a, action])
        db.commit()

        try:
            get_client_optimization_action_execution_preview(
                "client-a",
                "action-a",
                db=db,
                current=_current_user(org_b, user_b),
            )
        except HTTPException as exc:
            assert exc.status_code == 404
        else:
            raise AssertionError("Expected cross-workspace preview to be rejected")
