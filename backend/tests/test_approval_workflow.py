from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.deps import CurrentUser
from app.api.routers.clients import (
    list_client_optimization_action_events,
    save_optimization_plan_as_actions,
    update_client_optimization_action,
)
from app.db import Base
from app.models import ClientAccount, DirectCampaignPeriodStat, Organization, User
from app.schemas import OptimizationActionDraftUpdateStatus


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def test_save_plan_dedupes_and_status_change_records_events() -> None:
    SessionLocal = _session_factory()

    with SessionLocal() as db:
        org = Organization(id="org-1", name="Workspace")
        user = User(id="user-1", organization_id="org-1", email="user@example.com", provider="email")
        client = ClientAccount(id="client-1", organization_id="org-1", name="Client 1", segment="Test", target_cpa=1000)
        stat = DirectCampaignPeriodStat(
            client_id="client-1",
            campaign_id="campaign-1",
            campaign_name="Search Campaign",
            period_from=datetime(2026, 5, 1, tzinfo=UTC),
            period_to=datetime(2026, 5, 7, tzinfo=UTC),
            impressions=1000,
            clicks=100,
            cost=5000.0,
            ctr=10.0,
            avg_cpc=50.0,
            conversions=1.0,
            cost_per_conversion=5000.0,
        )
        db.add_all([org, user, client, stat])
        db.commit()
        current = CurrentUser(email="user@example.com", user=user, organization=org)

        first = save_optimization_plan_as_actions("client-1", db=db, current=current)
        second = save_optimization_plan_as_actions("client-1", db=db, current=current)

        assert len(first.actions) == 1
        assert len(second.actions) == 1
        assert first.actions[0].id == second.actions[0].id

        updated = update_client_optimization_action(
            "client-1",
            first.actions[0].id,
            OptimizationActionDraftUpdateStatus(status="approved", user_comment="Approve for manual review"),
            db=db,
            current=current,
        )
        events = list_client_optimization_action_events("client-1", first.actions[0].id, db=db, current=current)

        assert updated.status == "approved"
        assert updated.userComment == "Approve for manual review"
        assert [event.eventType for event in events] == ["created", "status_changed", "comment_added"]
