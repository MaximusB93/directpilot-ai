import json
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import (
    ClientAccount,
    ConnectedAccount,
    DirectCampaignPeriodStat,
    OAuthToken,
    Organization,
    SyncJob,
)
from app.services.ai_recommendations import build_client_ai_context_from_db


def _session_factory():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def test_server_ai_context_contains_evidence_without_tokens() -> None:
    SessionLocal = _session_factory()

    with SessionLocal() as db:
        org = Organization(id="org-1", name="Workspace")
        account = ConnectedAccount(
            id="account-1",
            organization_id="org-1",
            provider="yandex",
            external_user_id="external-1",
            login="direct-login",
            display_name="Direct Login",
            status="connected",
        )
        client = ClientAccount(
            id="client-1",
            organization_id="org-1",
            name="Client 1",
            segment="Test",
            direct_login="direct-login",
            metrica_counter="12345",
            yandex_account_id="account-1",
            target_cpa=1000,
            conversion_goal_ids="111, 222",
        )
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
            conversions=4.0,
            goal_ids="111,222",
            goal_conversions=2.0,
            goal_cpa=2500.0,
            conversion_source="metrika_goals",
        )
        job = SyncJob(
            id="sync-1",
            client_id="client-1",
            source_type="yandex_direct",
            status="success",
            rows_loaded=1,
        )
        token = OAuthToken(
            id="token-1",
            account_id="account-1",
            access_token_encrypted="encrypted-access-token-secret",
            refresh_token_encrypted="encrypted-refresh-token-secret",
        )
        db.add_all([org, account, client, stat, job, token])
        db.commit()

        context = build_client_ai_context_from_db(db, "client-1")

    assert context["client"]["id"] == "client-1"
    assert context["goals"]["selected_goal_ids"] == ["111", "222"]
    assert context["goals"]["has_goal_data"] is True
    assert context["yandex_binding"]["bound"] is True
    assert context["latest_sync_job"]["rows_loaded"] == 1
    assert context["campaigns"][0]["campaign_name"] == "Search Campaign"
    assert context["campaigns"][0]["goal_conversions"] == 2.0
    assert context["optimization_plan"]

    serialized = json.dumps(context, ensure_ascii=False)
    assert "encrypted-access-token-secret" not in serialized
    assert "encrypted-refresh-token-secret" not in serialized
    assert "access_token" not in serialized
    assert "refresh_token" not in serialized


def test_server_ai_context_can_focus_selected_campaign() -> None:
    SessionLocal = _session_factory()

    with SessionLocal() as db:
        db.add(Organization(id="org-1", name="Workspace"))
        db.add(ClientAccount(id="client-1", organization_id="org-1", name="Client 1", segment="Test"))
        for campaign_id, campaign_name in [("campaign-1", "Search Campaign"), ("campaign-2", "Brand Campaign")]:
            db.add(
                DirectCampaignPeriodStat(
                    client_id="client-1",
                    campaign_id=campaign_id,
                    campaign_name=campaign_name,
                    period_from=datetime(2026, 5, 1, tzinfo=UTC),
                    period_to=datetime(2026, 5, 7, tzinfo=UTC),
                    impressions=100,
                    clicks=10,
                    cost=1000.0,
                    ctr=10.0,
                    avg_cpc=100.0,
                    conversions=1.0,
                )
            )
        db.commit()

        context = build_client_ai_context_from_db(db, "client-1", selected_campaign_name="Brand Campaign")

    assert [item["campaign_name"] for item in context["campaigns"]] == ["Brand Campaign"]
    assert context["selected_campaign"]["campaign_name"] == "Brand Campaign"
